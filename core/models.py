from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class Side(str, Enum):
    """Trading order side."""
    BUY = "BUY"
    SELL = "SELL"


class Outcome(str, Enum):
    """Binary market outcomes."""
    YES = "YES"
    NO = "NO"


class OrderBookLevel(BaseModel):
    """Single price level in the order book."""
    price: float = Field(..., ge=0.0, le=1.0, description="Outcome price between 0.00 and 1.00")
    size: float = Field(..., gt=0.0, description="Available liquidity at this price level")


class OrderBook(BaseModel):
    """Live Polymarket CLOB Order Book structure."""
    market_id: str
    asset_id: str
    bids: List[OrderBookLevel] = []
    asks: List[OrderBookLevel] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SportsbookOdds(BaseModel):
    """Odds data from a traditional or crypto sportsbook."""
    bookmaker_name: str
    event_id: str
    outcome_name: str
    odds: float = Field(..., gt=1.0, description="Decimal odds (e.g., 2.15)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ArbitrageOpportunity(BaseModel):
    """Calculated arbitrage opportunity between Polymarket and a Sportsbook."""
    id: str
    event_name: str
    polymarket_asset_id: str
    polymarket_outcome: Outcome
    polymarket_price: float
    sportsbook_name: str
    sportsbook_odds: float
    raw_roi_percent: float
    net_roi_percent: float
    recommended_poly_stake: float
    recommended_sportsbook_stake: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
