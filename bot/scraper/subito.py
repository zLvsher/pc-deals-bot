"""Scraper per Subito.it (marketplace dell'usato più usato in Italia).

Comportamento del sito (studiato — vedi docs/MARKETPLACES.md):
  * La lista risultati è servita in HTML (SSR): ogni annuncio è un
    `<article data-id="...">` con titolo, prezzo e città. Funziona senza
    browser headless né login.
  * Protezione anti-bot: Cloudflare/light, basta uno User-Agent realistico
    e un rate-limit ragionevole. Se arriva un 403 serve il fallback Playwright
    (tracciato come TODO nel README).
  * URL di ricerca: https://www.subito.it/affari-usati-italia/tutti-i-annunci.htm?q=testo
    Filtri nativi usabili via querystring: `pz` (prezzo, es. "min-max"),
    `comune`/`provincia` per la zona (no vera geodistanza: approssimata con
    CAP/provincia e filtraggio lato nostro sulla città).
  * Spedizione vs scambio a mano: non è un filtro della SERP; si legge dai tag
    dell'articolo ("Spedizione") o dalla descrizione.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from bot.models import Category, Listing, SearchParams
from bot.scraper.base import BaseScraper

log = logging.getLogger("bot.scraper.subito")

_PRICE_RE = re.compile(r"(\d[\d.,]*)\s*€")


class SubitoScraper(BaseScraper):
    name = "subito"

    BASE = "https://www.subito.it"

    def _build_url(self, params: SearchParams) -> str:
        q = params.query.replace(" ", "+")
        price_filter = f"{int(params.min_price)}-{int(params.max_price)}"
        # /b/ è il path generico di ricerca su tutto il territorio
        return f"{self.BASE}/b/?q={q}&pz={price_filter}&fk=3"  # fk=3 = ordinati per recentezza

    async def search(self, params: SearchParams) -> list[Listing]:
        url = self._build_url(params)
        try:
            resp = await self.get(url)
        except Exception as exc:  # noqa: BLE001
            log.error("[subito] ricerca fallita: %s", exc)
            return []
        return self.parse_listings(resp.text, params.category)

    # separato per essere testabile senza rete
    def parse_listings(self, html: str, category: Category) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        out: list[Listing] = []
        for art in soup.select("article[data-id]"):
            ext_id = art.get("data-id", "")
            a = art.select_one("h2 a[href], a.plink[href]")
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a["href"]
            url = href if href.startswith("http") else self.BASE + href

            price_txt = ""
            p_el = art.select_one("p.price, .price")
            if p_el:
                price_txt = p_el.get_text(" ", strip=True)
            m = _PRICE_RE.search(price_txt)
            price = float(m.group(1).replace(".", "").replace(",", ".")) if m else -1.0

            city_el = art.select_one(".location-txt, p.location, .txt-location")
            city = city_el.get_text(" ", strip=True) if city_el else None

            blob = art.get_text(" ", strip=True).lower()
            shipping = "spedizione" in blob or "spedisco" in blob

            out.append(self.make_listing(
                external_id=ext_id, title=title, url=url, price=price,
                category=category, city=city, shipping=shipping,
                description=blob[:500],
            ))
        log.info("[subito] trovati %d annunci", len(out))
        return out
