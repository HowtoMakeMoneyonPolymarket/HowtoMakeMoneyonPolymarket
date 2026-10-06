from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime

class Base(DeclarativeBase):
    pass

class TradeModel(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(primary_key=True)
    event_name: Mapped[str]
    poly_stake: Mapped[float]
    sportsbook_stake: Mapped[float]
    net_roi: Mapped[float]
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class DatabaseManager:
    def __init__(self, db_url: str = "sqlite+aiosqlite:///spreadcore.db"):
        self.engine = create_async_engine(db_url, echo=False)
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init_db(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
