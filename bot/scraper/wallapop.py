"""Scraper per Wallapop.

Comportamento del sito (vedi docs/MARKETPLACES.md):
  * Frontend Next.js: la pagina di ricerca contiene uno stato JSON in
    `<script id="__NEXT_DATA__">` — lo parsiamo direttamente, niente browser.
  * GraphQL interno pubblico:
        POST https://www.wallapop.com/api/graphql (OperationName: GetSearch)
    richiedibile con semplici header; restituisce items con prezzo, titolo,
    slug, posizione (lat/lon!) — uno dei pochi siti che espone le coordinate,
    perfetto per il filtro raggio.
  * Qui usiamo l'approccio __NEXT_DATA__ (più stabile del GraphQL che cambia
    hash delle query frequentemente).
"""
from __future__ import annotations

import json
import logging
from urllib.parse import quote

from bot.models import Category, Listing, SearchParams
from bot.scraper.base import BaseScraper

log = logging.getLogger("bot.scraper.wallapop")


class WallapopScraper(BaseScraper):
    name = "wallapop"

    BASE = "https://www.wallapop.it"

    def _build_url(self, params: SearchParams) -> str:
        q = quote(params.query)
        extra = f"&min_price={int(params.min_price)}&max_price={int(params.max_price)}"
        return f"{self.BASE}/api/v4/search/?text={q}{extra}&sort_by=-created"

    async def search(self, params: SearchParams) -> list[Listing]:
        # Prima via: endpoint JSON di ricerca. Fallback: parsing __NEXT_DATA__.
        try:
            resp = await self.get(
                f"https://www.wallapop.com/it/search?text={quote(params.query)}",
            )
            html = resp.text
        except Exception as exc:  # noqa: BLE001
            log.error("[wallapop] ricerca fallita: %s", exc)
            return []
        return self.parse_html(html, params.category)

    def parse_html(self, html: str, category: Category) -> list[Listing]:
        idx = html.find('__NEXT_DATA__')
        if idx == -1:
            log.warning("[wallapop] __NEXT_DATA__ non trovato (layout cambiato?)")
            return []
        start = html.find(">", idx) + 1
        end = html.find("</script>", start)
        try:
            data = json.loads(html[start:end])
        except json.JSONDecodeError as exc:
            log.error("[wallapop] JSON embedded illeggibile: %s", exc)
            return []

        out: list[Listing] = []
        items = (data.get("props", {}).get("initialState", {})
                     .get("search", {}).get("items", []))
        for it in items:
            product = it.get("product") or it
            ext_id = product.get("id")
            title = product.get("title", "")
            if not ext_id or not title:
                continue
            price_val = float((product.get("price") or {}).get("amount",
                              product.get("price", 0)) or 0)
            loc = product.get("location") or {}
            lat, lon = loc.get("lat"), loc.get("lon")
            out.append(self.make_listing(
                external_id=ext_id,
                title=title,
                url=f"https://www.wallapop.it/product/{ext_id}",
                price=price_val,
                category=category,
                city=loc.get("address") or loc.get("city_name"),
                shipping=bool(product.get("shipping") or product.get("shipping")),
                description=(product.get("description") or "")[:500],
                lat=float(lat) if lat else None,
                lon=float(lon) if lon else None,
            ))
        log.info("[wallapop] trovati %d annunci", len(out))
        return out
