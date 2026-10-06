import time
import asyncio
import logging
from typing import Dict, Optional, Any
import aiohttp
from pydantic import BaseModel, Field

from config.settings import settings
from core.models import Side, Outcome

logger = logging.getLogger("SpreadCore.Execution")


class OrderRequest(BaseModel):
    """Payload model for submitting an order to Polymarket CLOB."""
    asset_id: str
    price: float = Field(..., ge=0.01, le=0.99)
    size: float = Field(..., gt=0.0)
    side: Side = Side.BUY
    outcome: Outcome = Outcome.YES
    is_maker: bool = True  # True for Limit (Maker), False for Market (Taker)


class OrderResponse(BaseModel):
    """Standardized response structure for placed orders."""
    order_id: str
    status: str  # "SUBMITTED", "FILLED", "PARTIALLY_FILLED", "CANCELLED", "FAILED"
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    error_message: Optional[str] = None


class PolymarketExecutionClient:
    """Non-custodial execution client interacting with Polymarket CLOB via Session Keys."""

    def __init__(self, api_url: str = settings.POLYMARKET_CLOB_API_URL, session_key: str = settings.POLYMARKET_SESSION_KEY):
        self.api_url = api_url
        self.session_key = session_key
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.session_key}",
                "User-Agent": "SpreadCore-Terminal/2.4.0"
            }
            self._http_session = aiohttp.ClientSession(headers=headers)
        return self._http_session

    async def place_order(self, order_req: OrderRequest) -> OrderResponse:
        """
        Submits an order to Polymarket CLOB API in one click.
        Uses Session Key authentication without needing private key access.
        """
        session = await self._get_session()
        endpoint = f"{self.api_url}/order"

        # Construct CLOB compliant order payload
        payload = {
            "asset_id": order_req.asset_id,
            "price": str(order_req.price),
            "size": str(order_req.size),
            "side": order_req.side.value,
            "order_type": "LIMIT" if order_req.is_maker else "MARKET",
            "timestamp": int(time.time() * 1000)
        }

        try:
            logger.info(f"[EXECUTION] Sending {payload['order_type']} order: {order_req.side.value} ${order_req.size} @ ${order_req.price}")
            
            # Simulated API call if no valid session key is provided
            if not self.session_key:
                logger.warning("[EXECUTION] No session key found. Simulating successful order placement.")
                await asyncio.sleep(0.05)  # Simulate 50ms latency
                return OrderResponse(
                    order_id=f"poly_ord_sim_{int(time.time()*1000)}",
                    status="FILLED" if not order_req.is_maker else "SUBMITTED",
                    filled_size=order_req.size if not order_req.is_maker else 0.0,
                    avg_fill_price=order_req.price
                )

            async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=2.0)) as response:
                if response.status in (200, 201):
                    data = await response.json()
                    return OrderResponse(
                        order_id=data.get("orderID", "unknown"),
                        status=data.get("status", "SUBMITTED"),
                        filled_size=float(data.get("filledSize", 0.0)),
                        avg_fill_price=float(data.get("price", order_req.price))
                    )
                else:
                    error_text = await response.text()
                    logger.error(f"[EXECUTION] Order failed with status {response.status}: {error_text}")
                    return OrderResponse(
                        order_id="",
                        status="FAILED",
                        error_message=f"HTTP {response.status}: {error_text}"
                    )

        except Exception as e:
            logger.error(f"[EXECUTION] Exception during order placement: {e}")
            return OrderResponse(
                order_id="",
                status="FAILED",
                error_message=str(e)
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Revokes an open order on Polymarket immediately."""
        session = await self._get_session()
        endpoint = f"{self.api_url}/order/{order_id}"

        try:
            logger.info(f"[AUTO-CANCEL] Revoking order: {order_id}")
            if not self.session_key:
                logger.info(f"[AUTO-CANCEL] Order {order_id} successfully cancelled (Simulated).")
                return True

            async with session.delete(endpoint, timeout=aiohttp.ClientTimeout(total=1.5)) as response:
                return response.status == 200

        except Exception as e:
            logger.error(f"[AUTO-CANCEL] Error revoking order {order_id}: {e}")
            return False

    async def close(self):
        """Close underlying HTTP session."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()


class ExecutionManager:
    """Manages active orders, risk protection, and auto-cancel workflows."""

    def __init__(self, client: PolymarketExecutionClient):
        self.client = client
        self.active_orders: Dict[str, OrderRequest] = {}  # order_id -> OrderRequest

    async def execute_one_click_trade(self, order_req: OrderRequest) -> OrderResponse:
        """One-click trigger for user UI action."""
        response = await self.client.place_order(order_req)
        
        if response.status in ("SUBMITTED", "PARTIALLY_FILLED"):
            self.active_orders[response.order_id] = order_req
            
        return response

    async def monitor_and_autocancel(self, order_id: str, current_sportsbook_odds: float, target_min_odds: float):
        """
        Auto-Cancel Guard:
        If sportsbook odds drop below threshold while Polymarket limit order is pending,
        cancel the order immediately to prevent unhedged single-leg exposure.
        """
        if current_sportsbook_odds < target_min_odds:
            logger.warning(
                f"🚨 [RISK ENGINE] Sportsbook odds dropped to {current_sportsbook_odds} (Min required: {target_min_odds}). "
                f"Triggering Auto-Cancel for Order {order_id}!"
            )
            success = await self.client.cancel_order(order_id)
            if success and order_id in self.active_orders:
                del self.active_orders[order_id]
            return True
        return False
