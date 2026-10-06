import os
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application settings and configuration management."""

    # Application Info
    APP_NAME: str = "SpreadCore Terminal"
    VERSION: str = "2.4.0-stable"
    DEBUG: bool = False

    # Polygon & Polymarket Credentials
    POLYGON_RPC_URL: str = Field(
        default="https://polygon-rpc.com",
        description="RPC endpoint for Polygon network"
    )
    POLYMARKET_CLOB_API_URL: str = "https://clob.polymarket.com"
    POLYMARKET_WS_URL: str = "wss://ws-subscriptions.polymarket.com/ws/market"
    POLYMARKET_SESSION_KEY: str = Field(
        default="",
        description="Session API key for non-custodial execution"
    )

    # Risk Engine Controls
    MIN_ROI_PERCENT: float = Field(
        default=1.5,
        description="Minimum ROI threshold to trigger trade signal"
    )
    MAX_POSITION_SIZE_USD: float = Field(
        default=500.0,
        description="Maximum capital allocation per trade leg"
    )
    KICKOFF_GUARD_MINUTES: int = Field(
        default=5,
        description="Auto-cancel pending orders N minutes before event start"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
