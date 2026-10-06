import json
import asyncio
import logging
from typing import Dict, Callable, Optional, List
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from config.settings import settings
from core.models import OrderBook, OrderBookLevel, SportsbookOdds, ArbitrageOpportunity, Outcome
from services.calculator import HedgeCalculator

# Configure logger for low-latency tracing
logger = logging.getLogger("SpreadCore.Scanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class PolymarketWSClient:
    """High-frequency WebSocket client for Polymarket CLOB order book feed."""

    def __init__(self, ws_url: str = settings.POLYMARKET_WS_URL):
        self.ws_url = ws_url
        self._connection: Optional[websockets.WebSocketClientProtocol] = None
        self._is_running: bool = False
        self._subscribed_assets: List[str] = []
        self._on_book_update_callback: Optional[Callable[[OrderBook], None]] = None

    def set_on_book_update_callback(self, callback: Callable[[OrderBook], None]) -> None:
        """Register a callback to handle parsed order book updates."""
        self._on_book_update_callback = callback

    async def connect(self, asset_ids: List[str]) -> None:
        """
        Connect to Polymarket WS and subscribe to order book updates for asset IDs.
        Includes automatic retry logic with exponential backoff.
        """
        self._subscribed_assets = asset_ids
        self._is_running = True
        retry_delay = 1.0

        while self._is_running:
            try:
                logger.info(f"Connecting to Polymarket WebSocket: {self.ws_url}")
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=10_000_000
                ) as ws:
                    self._connection = ws
                    logger.info("Connected to Polymarket WebSocket successfully.")
                    retry_delay = 1.0  # Reset retry delay on successful connection

                    # Send subscription payload
                    await self._subscribe(asset_ids)

                    # Listen for incoming messages
                    await self._listen()

            except (ConnectionClosedError, ConnectionClosedOK) as e:
                logger.warning(f"WebSocket connection closed: {e}. Reconnecting in {retry_delay}s...")
            except Exception as e:
                logger.error(f"Unexpected WebSocket error: {e}. Reconnecting in {retry_delay}s...")

            if self._is_running:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)  # Cap exponential backoff at 30 seconds

    async def _subscribe(self, asset_ids: List[str]) -> None:
        """Send market subscription request to Polymarket CLOB WS."""
        payload = {
            "type": "market",
            "assets_ids": asset_ids,
            "channel": "book"
        }
        if self._connection:
            await self._connection.send(json.dumps(payload))
            logger.info(f"Subscribed to assets: {asset_ids}")

    async def _listen(self) -> None:
        """Process incoming WebSocket frames with minimal latency."""
        if not self._connection:
            return

        async for message in self._connection:
            try:
                data = json.loads(message)
                order_book = self._parse_book_message(data)
                if order_book and self._on_book_update_callback:
                    # Fire-and-forget or await callback execution
                    if asyncio.iscoroutinefunction(self._on_book_update_callback):
                        await self._on_book_update_callback(order_book)
                    else:
                        self._on_book_update_callback(order_book)
            except json.JSONDecodeError:
                logger.error("Failed to decode WS JSON payload.")
            except Exception as e:
                logger.error(f"Error processing WS message: {e}")

    def _parse_book_message(self, data: dict) -> Optional[OrderBook]:
        """Convert raw Polymarket JSON frame into standard OrderBook model."""
        event_type = data.get("event_type")
        if event_type not in ("book", "price_change"):
            return None

        asset_id = data.get("asset_id", "")
        market_id = data.get("market", "")

        raw_bids = data.get("bids", [])
        raw_asks = data.get("asks", [])

        bids = [
            OrderBookLevel(price=float(item["price"]), size=float(item["size"]))
            for item in raw_bids
        ]
        asks = [
            OrderBookLevel(price=float(item["price"]), size=float(item["size"]))
            for item in raw_asks
        ]

        # Sort order book: bids descending, asks ascending
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)

        return OrderBook(
            market_id=market_id,
            asset_id=asset_id,
            bids=bids,
            asks=asks
        )

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket connection."""
        self._is_running = False
        if self._connection:
            await self._connection.close()
            logger.info("Polymarket WebSocket disconnected.")


class ArbitrageScannerEngine:
    """Engine responsible for matching Polymarket order books with Sportsbook odds."""

    def __init__(self, calculator: HedgeCalculator):
        self.calculator = calculator
        self.sportsbook_cache: Dict[str, SportsbookOdds] = {}  # key: market_mapping_id
        self.poly_books: Dict[str, OrderBook] = {}              # key: asset_id

    def update_sportsbook_odds(self, mapping_id: str, odds: SportsbookOdds) -> None:
        """Update live sportsbook cache for a specific mapped event."""
        self.sportsbook_cache[mapping_id] = odds

    async def process_polymarket_update(self, book: OrderBook, mapping_id: str) -> Optional[ArbitrageOpportunity]:
        """
        Evaluate real-time order book update against stored sportsbook odds.
        
        :param book: Fresh OrderBook instance from WebSocket
        :param mapping_id: Event identifier linking Polymarket asset to Sportsbook line
        """
        self.poly_books[book.asset_id] = book

        sportsbook_odds = self.sportsbook_cache.get(mapping_id)
        if not sportsbook_odds or not book.asks:
            return None

        # Best available ask price on Polymarket (cheapest price to buy outcome)
        best_ask = book.asks[0]
        poly_price = best_ask.price

        # Check if available liquidity meets minimum allocation
        if (best_ask.price * best_ask.size) < 10.0:  # Ignore microscopic depth < $10
            return None

        try:
            # Calculate delta-neutral hedge
            calc_result = self.calculator.calculate_hedged_stake(
                poly_price=poly_price,
                sportsbook_odds=sportsbook_odds.odds,
                target_poly_stake=min(settings.MAX_POSITION_SIZE_USD, best_ask.price * best_ask.size)
            )

            net_roi = calc_result["net_roi_percent"]

            # Filter out opportunities below configured minimum ROI threshold
            if net_roi >= settings.MIN_ROI_PERCENT:
                opp = ArbitrageOpportunity(
                    id=f"{book.asset_id}_{sportsbook_odds.bookmaker_name}_{int(book.timestamp.timestamp())}",
                    event_name=f"Mapped Event [{mapping_id}]",
                    polymarket_asset_id=book.asset_id,
                    polymarket_outcome=Outcome.YES,
                    polymarket_price=poly_price,
                    sportsbook_name=sportsbook_odds.bookmaker_name,
                    sportsbook_odds=sportsbook_odds.odds,
                    raw_roi_percent=net_roi,
                    net_roi_percent=net_roi,
                    recommended_poly_stake=calc_result["poly_stake"],
                    recommended_sportsbook_stake=calc_result["sportsbook_stake"]
                )
                return opp

        except ValueError as e:
            logger.debug(f"Calculation error: {e}")

        return None
