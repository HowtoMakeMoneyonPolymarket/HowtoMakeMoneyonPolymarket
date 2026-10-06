from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any

from services.order_executor import OrderRequest, OrderResponse
from api.websocket_server import ws_manager

router = APIRouter(prefix="/api/v1", tags=["Terminal API"])


class ExecutionPayload(BaseModel):
    asset_id: str
    price: float
    size: float
    side: str = "BUY"


@router.get("/health")
async def health_check():
    """Health check endpoint for container orchestrators."""
    return {"status": "ok", "service": "SpreadCore Terminal Engine"}


@router.get("/pnl/summary")
async def get_pnl_summary():
    """Returns current portfolio performance, realized PnL, and win-rate statistics."""
    # Access PnL Tracker via global app state
    from main import terminal_app
    if not terminal_app:
        raise HTTPException(status_code=503, detail="Terminal engine initializing...")
    return terminal_app.pnl_tracker.get_summary_analytics()


@router.post("/trade/execute", response_model=OrderResponse)
async def execute_trade(payload: ExecutionPayload):
    """Triggers direct One-Click order execution from Web UI or external signals."""
    from main import terminal_app
    if not terminal_app:
        raise HTTPException(status_code=503, detail="Terminal engine offline.")

    from core.models import Side, Outcome
    order_req = OrderRequest(
        asset_id=payload.asset_id,
        price=payload.price,
        size=payload.size,
        side=Side(payload.side.upper()),
        outcome=Outcome.YES,
        is_maker=True
    )
    
    response = await terminal_app.exec_manager.execute_one_click_trade(order_req)
    return response


@router.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time stream for spreads, live order books, and trade fill events."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep-alive receive loop
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
