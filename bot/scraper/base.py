"""Classe base per tutti gli scraper dei marketplace.

Ogni sito ha un adattamento diverso (API interna, HTML SSR, JSON embedded):
questa classe incapsula le parti comuni — client HTTP, user-agent, retry,
rate-limiting "educato" e normalizzazione dei risultati in `Listing`.
"""
from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from bot.models import Category, Listing, SearchParams

log = logging.getLogger("bot.scraper")

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class BaseScraper(ABC):
    """Contratto: dato un SearchParams, produce una lista di Listing normalizzati."""

    name: str = "base"
    # Pausa minima/massima tra una richiesta e l'altra (anti-ban, educazione)
    min_delay: float = 1.5
    max_delay: float = 4.0

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._own_client = client is None
        self.client = client or httpx.AsyncClient(
            headers=self.headers(),
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
        )
        self._lock = asyncio.Lock()
        self._last_request: float = 0.0

    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": DESKTOP_UA,
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        }

    async def _throttle(self) -> None:
        """Rate limiting per-instance: evita raffiche di richieste allo stesso sito."""
        async with self._lock:
            now = asyncio.get_running_loop().time()
            wait = self._last_request + random.uniform(self.min_delay, self.max_delay) - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = asyncio.get_running_loop().time()

    async def get(self, url: str, **kwargs) -> httpx.Response:
        await self._throttle()
        resp = await self.client.get(url, **kwargs)
        log.debug("[%s] GET %s -> %s", self.name, url, resp.status_code)
        if resp.status_code in (403, 429):
            log.warning(
                "[%s] Il sito sta bloccando lo scraping (%s). "
                "Vedi docs/MARKETPLACES.md per le contromisure.",
                self.name, resp.status_code,
            )
        resp.raise_for_status()
        return resp

    @abstractmethod
    async def search(self, params: SearchParams) -> list[Listing]:
        """Esegue la ricerca sul marketplace e restituisce annunci normalizzati."""

    def make_listing(self, *, external_id: str, title: str, url: str, price: float,
                     category: Category, city: str | None = None,
                     shipping: bool = False, description: str = "",
                     lat: float | None = None, lon: float | None = None) -> Listing:
        return Listing(
            source=self.name,
            external_id=str(external_id),
            title=title.strip(),
            url=url,
            price=price,
            category=category,
            city=city,
            shipping=shipping,
            raw_description=description,
            lat=lat,
            lon=lon,
        )

    async def aclose(self) -> None:
        if self._own_client:
            await self.client.aclose()
