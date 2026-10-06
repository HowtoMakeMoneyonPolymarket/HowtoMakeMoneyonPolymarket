import asyncio
import logging
from typing import Dict, Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from config.settings import settings
from services.order_executor import ExecutionManager

logger = logging.getLogger("SpreadCore.Safety")


class EventScheduleInfo(BaseModel):
    """Event scheduling details required for time-based safety checks."""
    event_id: str
    event_name: str
    kickoff_time: datetime
    is_live: bool = False


class SafetyCheckResult(BaseModel):
    """Result structure for continuous risk validation."""
    is_safe: bool
    reason: Optional[str] = None


class KickoffGuard:
    """Monitors scheduled event start times and cancels pending orders before kickoff."""

    def __init__(self, guard_minutes: int = settings.KICKOFF_GUARD_MINUTES):
        self.guard_seconds = guard_minutes * 60
        self.monitored_events: Dict[str, EventScheduleInfo] = {}

    def register_event(self, event_info: EventScheduleInfo) -> None:
        """Register an event for kickoff safety tracking."""
        self.monitored_events[event_info.event_id] = event_info

    def is_kickoff_imminent(self, event_id: str) -> bool:
        """
        Evaluates whether an event is too close to kickoff time or already in-play.
        """
        event = self.monitored_events.get(event_id)
        if not event:
            return False

        if event.is_live:
            return True

        now_utc = datetime.now(timezone.utc)
        # Handle naive or aware datetime objects
        kickoff = event.kickoff_time if event.kickoff_time.tzinfo else event.kickoff_time.replace(tzinfo=timezone.utc)
        time_to_kickoff = (kickoff - now_utc).total_seconds()

        if time_to_kickoff <= self.guard_seconds:
            logger.warning(
                f"🚨 [KICKOFF GUARD] Event '{event.event_name}' is within safety window "
                f"({round(time_to_kickoff / 60, 2)} minutes to start). Blocked execution!"
            )
            return True

        return False


class ForkSafetyController:
    """Real-time monitoring engine for active orders and risk parameters."""

    def __init__(self, execution_manager: ExecutionManager, kickoff_guard: KickoffGuard):
        self.exec_manager = execution_manager
        self.kickoff_guard = kickoff_guard
        self.max_daily_loss = 100.0  # Maximum daily loss in USD
        self.current_daily_loss = 0.0
        self.circuit_breaker_triggered = False

    def validate_pre_execution(self, event_id: str) -> SafetyCheckResult:
        """
        Runs comprehensive pre-flight safety check prior to placing a trade.
        """
        if self.circuit_breaker_triggered:
            return SafetyCheckResult(
                is_safe=False,
                reason="Circuit breaker active! Daily loss threshold reached."
            )

        if self.kickoff_guard.is_kickoff_imminent(event_id):
            return SafetyCheckResult(
                is_safe=False,
                reason="Kickoff guard active. Trade blocked close to event start."
            )

        return SafetyCheckResult(is_safe=True)

    async def auto_cancel_if_fork_disappears(
        self,
        order_id: str,
        current_poly_ask: float,
        target_max_poly_ask: float
    ) -> bool:
        """
        Validates if Polymarket order book price moved away from trade parameters.
        If price changed beyond tolerance, auto-cancel order immediately.
        """
        if current_poly_ask > target_max_poly_ask:
            logger.warning(
                f"🚨 [FORK DISAPPEARED] Polymarket price slipped to ${current_poly_ask} "
                f"(Max acceptable: ${target_max_poly_ask}). Auto-cancelling order {order_id}!"
            )
            return await self.exec_manager.client.cancel_order(order_id)
        return False

    def record_loss(self, loss_amount: float) -> None:
        """Update daily loss tracker and trigger circuit breaker if threshold is exceeded."""
        self.current_daily_loss += loss_amount
        if self.current_daily_loss >= self.max_daily_loss:
            self.circuit_breaker_triggered = True
            logger.critical(
                f"🛑 [CIRCUIT BREAKER TRIGGERED] Total loss (${self.current_daily_loss}) "
                f"exceeded maximum allowed (${self.max_daily_loss}). Systems locked!"
            )
