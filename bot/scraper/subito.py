"""Scraper per Subito.it (marketplace dell'usato più usato in Italia).

Comportamento del sito (studiato e verificato — vedi docs/MARKETPLACES.md):
  * I vecchi path di ricerca (`/b/?q=...`, `/annunci-italia/vendi/...`) non
    esistono più: rispondono 403/404 o con la pagina "Servizio non
    disponibile". Il path valido è:
        https://www.subito.it/annunci-italia/vendita/usato/?q=<testo>
    con filtri nativi via querystring:
        pz=min-max   prezzo      ·  fk=3  ordinamento per recentezza
        shp=true     solo con spedizione
  * Protezione anti-bot: arriva un 403 "light" alle richieste httpx classiche
    (fingerprint TLS riconoscibile). Soluzione adottata: `curl_cffi` con
    impersonazione Chrome (TLS + header realistici) → 200 affidabile.
  * La lista risultati è servita in HTML (SSR, Next.js): ogni annuncio è un
    `<article>` SENZA data-id; il vero id è nel finale dell'href
    (es. `...-milano-661964130.htm`). Titolo in `h3`, prezzo in
    `[class*=price]`, città in `[class*=location]`, spedizione deducibile dal
    badge "Spedizione disponibile" nel testo della card.
  * Nota rilevanza: la q di Subito matcha anche le descrizioni, quindi
    ritornano fuori-tema (es. interi PC gaming): il filtro di pertinenza
    titolo->query è in bot/analysis/value.py.
"""
from __future__ import annotations

import asyncio
import logging
import re

from bs4 import BeautifulSoup

from bot.models import Category, Listing, SearchParams, ShippingMode
from bot.scraper.base import BaseScraper

log = logging.getLogger("bot.scraper.subito")

_PRICE_RE = re.compile(r"(\d[\d.,]*)\s*€")
_ID_RE = re.compile(r"-(\d{6,})\.htm")


def _http_get(url: str, timeout: float = 25.0) -> tuple[int, str]:
    """GET con browser-impersonation (aggira il 403 'lemuri' di Subito)."""
    from curl_cffi.requests import Session  # import pigro: deps opzionale
    with Session(impersonate="chrome124", timeout=timeout) as s:
        r = s.get(url)
        return r.status_code, r.text


class SubitoScraper(BaseScraper):
    name = "subito"

    BASE = "https://www.subito.it"
    SEARCH_PATH = "/annunci-italia/vendita/usato/"

    def _build_url(self, params: SearchParams) -> str:
        from urllib.parse import quote_plus
        q = quote_plus(params.query)              # maiuscole/minuscole gestite qui sotto
        price = f"{int(max(0, params.min_price))}-{int(max(1, params.max_price))}"
        url = f"{self.BASE}{self.SEARCH_PATH}?q={q}&pz={price}&fk=3"
        if params.shipping == ShippingMode.SHIP:
            url += "&shp=true"                    # filtro nativo "spedisce"
        return url

    async def search(self, params: SearchParams) -> list[Listing]:
        url = self._build_url(params)
        try:
            status, html = await asyncio.to_thread(_http_get, url)
        except Exception as exc:  # noqa: BLE001
            log.error("[subito] richiesta fallita: %s", exc)
            return []
        if status != 200 or "<article" not in html:
            log.warning("[subito] HTTP %s senza annunci (anti-bot?).", status)
            return []
        listings = self.parse_listings(html, params.category)
        # pre-filtro di pertinenza lato scraper (case-insensitive sul titolo):
        # scarta i fuori-tema che passano comunque la q di Subito
        toks = [t for t in re.split(r"[^\w]+", params.query.lower()) if len(t) > 2]
        if toks:
            listings = [l for l in listings
                        if any(t in l.title.lower() for t in toks)]
        log.info("[subito] %d annunci pertinenti dopo il pre-filtro", len(listings))
        return listings

    # separato per essere testabile senza rete
    def parse_listings(self, html: str, category: Category) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        out: list[Listing] = []
        for art in soup.find_all("article"):
            a = art.select_one("a[href*='.htm']")
            if not a:
                continue
            href = a["href"]
            url = href if href.startswith("http") else self.BASE + href
            m = _ID_RE.search(url)
            ext_id = m.group(1) if m else url

            t_el = art.select_one("h3, [class*=subject]")
            title = t_el.get_text(" ", strip=True) if t_el else a.get("aria-label", "")
            if not title:
                continue

            p_el = art.select_one("[class*=price]")
            pm = _PRICE_RE.search(p_el.get_text(" ", strip=True)) if p_el else None
            price = float(pm.group(1).replace(".", "").replace(",", ".")) if pm else -1.0

            loc_el = art.select_one("[class*=location]")
            city = re.sub(r"\s+", " ", loc_el.get_text(" ", strip=True)) if loc_el else None
            if city:
                city = re.sub(r"\s*\(.{1,4}\)\s*$", "", city).strip()

            blob = art.get_text(" ", strip=True).lower()
            shipping = "spedizione" in blob or "spedisco" in blob

            out.append(self.make_listing(
                external_id=ext_id, title=title, url=url, price=price,
                category=category, city=city, shipping=shipping,
                description=blob[:500],
            ))
        log.info("[subito] trovati %d annunci", len(out))
        return out
