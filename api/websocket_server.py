import logging
from typing import List
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("SpreadCore.API.WS")


class ConnectionManager:
    """Manages active WebSocket connections to broadcast terminal events."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS SERVER] New client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[WS SERVER] Client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcasts JSON payload to all active frontend subscribers."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[WS SERVER] Failed to send message to client: {e}")
                self.disconnect(connection)


ws_manager = ConnectionManager()
