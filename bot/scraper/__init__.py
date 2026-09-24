"""Registry degli scraper: aggiunge/rimuove marketplace in un solo punto."""
from __future__ import annotations

import logging

from bot.scraper.base import BaseScraper
from bot.scraper.demo import DemoScraper
from bot.scraper.facebook import FacebookScraper
from bot.scraper.subito import SubitoScraper
from bot.scraper.vinted import VintedScraper
from bot.scraper.wallapop import WallapopScraper

log = logging.getLogger("bot.registry")

# source name -> classe. Per aggiungere un sito: scrivere lo scraper e qui.
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    SubitoScraper.name: SubitoScraper,
    VintedScraper.name: VintedScraper,
    WallapopScraper.name: WallapopScraper,
    FacebookScraper.name: FacebookScraper,   # stub sperimentale
    DemoScraper.name: DemoScraper,           # sviluppo/test offline
}


def available_sources() -> list[str]:
    return sorted(SCRAPER_REGISTRY.keys())


def build_scrapers(sources: list[str]) -> list[BaseScraper]:
    """Istanzia gli scraper richiesti; ignora i nomi sconosciuti con warning."""
    out: list[BaseScraper] = []
    for s in sources:
        cls = SCRAPER_REGISTRY.get(s.lower())
        if cls is None:
            log.warning("source sconosciuta '%s' — ignorata", s)
            continue
        out.append(cls())
    return out
