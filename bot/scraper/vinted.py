"""Scraper per Vinted.

Comportamento del sito (vedi docs/MARKETPLACES.md):
  * Il frontend è una SPA, ma espone un'API JSON interna non documentata:
        GET https://www.vinted.it/api/v2/catalog
            ?search_text=...&currency=EUR&order=latest
            &price_from=..&price_to=..
    con header `X-Requested-With: XMLHttpRequest` e i cookie di sessione
    ottenuti aprendo prima la homepage. Risponde `{"items": [...]}`.
  * Ogni item ha: id, title, price (in centesimi), city (via user/profile),
    "can_be_sent" (spedizione) ecc.
  * Vinted è pensato per l'abbigliamento: RAM/CPU si trovano nella sezione
    elettronica/elettrodomestici, pochi risultati ma prezzi spesso bassi.
  * Anti-bot: rate-limit aggressivo → qui il throttle della base class è
    fondamentale; in alternativa usare l'app mobile API.
"""
from __future__ import annotations

import logging

import httpx

from bot.models import Category, Listing, SearchParams
from bot.scraper.base import BaseScraper

log = logging.getLogger("bot.scraper.vinted")


class VintedScraper(BaseScraper):
    name = "vinted"
    min_delay = 3.0   # Vinted è il più sensibile al rate-limiting
    max_delay = 7.0

    API = "https://www.vinted.it/api/v2/catalog"

    async def _warm_session(self) -> None:
        """Ottiene i cookie di sessione aprendo la homepage (necessari per l'API)."""
        try:
            await self.client.get("https://www.vinted.it/", timeout=15)
        except httpx.HTTPError:
            pass  # meglio procedere comunque: a volte l'API risponde senza cookie

    async def search(self, params: SearchParams) -> list[Listing]:
        await self._warm_session()
        query = {
            "search_text": params.query,
            "currency": "EUR",
            "order": "latest",
            "page": 1,
            "per_page": 36,
        }
        if params.min_price > 0:
            query["price_from"] = int(params.min_price * 100)  # centesimi
        if params.max_price > 0:
            query["price_to"] = int(params.max_price * 100)

        try:
            resp = await self.get(
                self.API, params=query,
                headers={"X-Requested-With": "XMLHttpRequest",
                         "Accept": "application/json"},
            )
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.error("[vinted] ricerca fallita: %s", exc)
            return []
        return self.parse_items(data, params.category)

    def parse_items(self, data: dict, category: Category) -> list[Listing]:
        out: list[Listing] = []
        for entry in data.get("items", []) or []:
            it = entry.get("item") or {}
            ext_id = it.get("id") or entry.get("id")
            title = it.get("title", "")
            if not ext_id or not title:
                continue
            price_cents = (it.get("price") or 0) / 100.0
            urls = it.get("urls") or {}
            slug = urls.get("web", "")
            url = f"https://www.vinted.it/catalog/{ext_id}-{slug}" if slug \
                else f"https://www.vinted.it/item/{ext_id}"
            city = ((entry.get("user") or {}).get("city")
                    or (entry.get("user") or {}).get("country_code"))
            shipping = bool(it.get("can_be_sent"))
            out.append(self.make_listing(
                external_id=ext_id, title=title, url=url, price=price_cents,
                category=category, city=city, shipping=shipping,
                description=(it.get("description") or "")[:500],
            ))
        log.info("[vinted] trovati %d annunci", len(out))
        return out
