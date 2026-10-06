import aiohttp
import logging

logger = logging.getLogger("SpreadCore.Telegram")

class TelegramNotifier:
    """Instant alert manager for trades, errors, and daily summaries."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async def send_alert(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=2.0) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send notification: {e}")
            return False
