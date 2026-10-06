import aiohttp
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("SpreadCore.Proxy")

class ProxyAccountManager:
    """Manages dedicated proxies and account sessions for anti-detect execution."""

    def __init__(self, proxies: List[str]):
        self.proxies = proxies
        self._proxy_index = 0

    def get_next_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        proxy = self.proxies[self._proxy_index % len(self.proxies)]
        self._proxy_index += 1
        return proxy

    async def create_client_session(self, proxy: Optional[str] = None) -> aiohttp.ClientSession:
        selected_proxy = proxy or self.get_next_proxy()
        connector = aiohttp.TCPConnector(ssl=False)
        return aiohttp.ClientSession(connector=connector, trust_env=True)
