from core.models import ArbitrageOpportunity, Outcome


class HedgeCalculator:
    """Smart Hedge Calculator for delta-neutral arbitrage execution."""

    def __init__(self, default_maker_rebate_rate: float = 0.002, default_bookmaker_fee_rate: float = 0.000):
        """
        Initialize calculator with default fee and rebate parameters.
        
        :param default_maker_rebate_rate: Polymarket maker rebate rate (e.g., 0.2% = 0.002)
        :param default_bookmaker_fee_rate: Bookmaker fee or withdrawal tax rate
        """
        self.maker_rebate_rate = default_maker_rebate_rate
        self.bookmaker_fee_rate = default_bookmaker_fee_rate

    def calculate_hedged_stake(
        self,
        poly_price: float,
        sportsbook_odds: float,
        target_poly_stake: float
    ) -> dict:
        """
        Calculate exact opposing sportsbook stake to ensure equal payout regardless of outcome.
        
        Formula:
        Net ROI = (Payout - Total Capital Outlay + Rebate - Fees) / Total Outlay * 100%
        """
        if poly_price <= 0 or poly_price >= 1:
            raise ValueError("Polymarket price must be strictly between 0 and 1.")
        if sportsbook_odds <= 1.0:
            raise ValueError("Sportsbook decimal odds must be greater than 1.0.")

        # Polymarket potential payout (Each winning share pays out $1.00)
        shares_bought = target_poly_stake / poly_price
        poly_payout = shares_bought * 1.0

        # Calculate required Sportsbook stake to match Polymarket payout
        # Sportsbook Payout = Sportsbook Stake * Sportsbook Odds
        sportsbook_stake = poly_payout / sportsbook_odds

        # Financial breakdown
        poly_rebate = target_poly_stake * self.maker_rebate_rate
        bookmaker_fee = sportsbook_stake * self.bookmaker_fee_rate
        total_outlay = target_poly_stake + sportsbook_stake

        # Net Profit Calculation
        guaranteed_payout = poly_payout
        net_profit = guaranteed_payout - total_outlay + poly_rebate - bookmaker_fee
        net_roi = (net_profit / total_outlay) * 100.0

        return {
            "poly_stake": round(target_poly_stake, 2),
            "sportsbook_stake": round(sportsbook_stake, 2),
            "total_outlay": round(total_outlay, 2),
            "expected_payout": round(guaranteed_payout, 2),
            "net_profit": round(net_profit, 2),
            "net_roi_percent": round(net_roi, 2),
            "maker_rebate_usd": round(poly_rebate, 4)
        }
