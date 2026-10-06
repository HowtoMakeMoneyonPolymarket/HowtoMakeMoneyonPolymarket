import uuid
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from core.models import Outcome

logger = logging.getLogger("SpreadCore.PnL")


class TradeStatus(str):
    OPEN = "OPEN"
    RESOLVED_POLYMARKET_WIN = "RESOLVED_POLYMARKET_WIN"
    RESOLVED_SPORTSBOOK_WIN = "RESOLVED_SPORTSBOOK_WIN"
    CANCELLED = "CANCELLED"


class TradeCard(BaseModel):
    """Represents a completed or active dual-leg arbitrage position."""
    trade_id: str = Field(default_factory=lambda: f"tc_{uuid.uuid4().hex[:8]}")
    event_name: str
    polymarket_asset_id: str
    
    # Polymarket Leg
    poly_stake: float
    poly_price: float
    poly_shares: float
    
    # Sportsbook Leg
    sportsbook_name: str
    sportsbook_stake: float
    sportsbook_odds: float
    
    # Financial metrics
    maker_rebate_usd: float = 0.0
    bookmaker_bonus_usd: float = 0.0
    expected_profit: float
    actual_profit: Optional[float] = None
    status: str = TradeStatus.OPEN
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None


class PnLTracker:
    """Tracks overall portfolio performance, win rates, and aggregated metrics."""

    def __init__(self):
        self.trades: Dict[str, TradeCard] = {}

    def record_trade(self, trade: TradeCard) -> None:
        """Stores a newly executed dual-leg trade."""
        self.trades[trade.trade_id] = trade
        logger.info(f"[PnL] Recorded new trade #{trade.trade_id} on {trade.event_name}")

    def resolve_trade(self, trade_id: str, polymarket_won: bool) -> TradeCard:
        """
        Calculates final PnL based on event outcome.
        
        If Polymarket won: Payout = Shares * $1.00 - Sportsbook Stake + Rebate
        If Sportsbook won: Payout = Sportsbook Stake * Odds - Polymarket Outlay + Rebate
        """
        trade = self.trades.get(trade_id)
        if not trade:
            raise KeyError(f"Trade ID {trade_id} not found in PnL tracker.")

        total_outlay = trade.poly_stake + trade.sportsbook_stake

        if polymarket_won:
            trade.status = TradeStatus.RESOLVED_POLYMARKET_WIN
            gross_payout = trade.poly_shares * 1.0
        else:
            trade.status = TradeStatus.RESOLVED_SPORTSBOOK_WIN
            gross_payout = trade.sportsbook_stake * trade.sportsbook_odds

        # Actual Net Profit = Gross Payout - Capital Outlay + Maker Rebates + Bookmaker Bonuses
        trade.actual_profit = round(
            gross_payout - total_outlay + trade.maker_rebate_usd + trade.bookmaker_bonus_usd, 2
        )
        trade.resolved_at = datetime.utcnow()

        logger.info(
            f"[PnL RESOLVE] Trade #{trade_id} resolved! "
            f"Winner: {'Polymarket' if polymarket_won else trade.sportsbook_name} | "
            f"Actual Profit: ${trade.actual_profit}"
        )
        return trade

    def get_summary_analytics(self) -> dict:
        """Computes aggregate analytics for dashboard display."""
        total_trades = len(self.trades)
        resolved_trades = [t for t in self.trades.values() if t.actual_profit is not None]
        
        total_volume = sum(t.poly_stake + t.sportsbook_stake for t in self.trades.values())
        total_realized_pnl = sum(t.actual_profit for t in resolved_trades)
        total_rebates = sum(t.maker_rebate_usd for t in self.trades.values())
        total_bonuses = sum(t.bookmaker_bonus_usd for t in self.trades.values())

        avg_roi = (total_realized_pnl / total_volume * 100) if total_volume > 0 else 0.0

        return {
            "total_trades_executed": total_trades,
            "resolved_trades": len(resolved_trades),
            "total_volume_usd": round(total_volume, 2),
            "realized_pnl_usd": round(total_realized_pnl, 2),
            "total_maker_rebates_usd": round(total_rebates, 2),
            "total_bookmaker_bonuses_usd": round(total_bonuses, 2),
            "overall_roi_percent": round(avg_roi, 2)
        }


class AutoResolver:
    """Mock/Integration service for fetching match results and triggering settlement."""

    def __init__(self, pnl_tracker: PnLTracker):
        self.tracker = pnl_tracker

    async def auto_resolve_event(self, trade_id: str, simulated_winning_outcome: Outcome):
        """Auto-resolves trade cards by matching outcome against Polymarket YES/NO."""
        poly_won = (simulated_winning_outcome == Outcome.YES)
        return self.tracker.resolve_trade(trade_id, polymarket_won=poly_won)
