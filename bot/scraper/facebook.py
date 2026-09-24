"""Facebook Marketplace — nota di progetto.

FB Marketplace NON è raggiungibile con semplice HTTP: richiede login, usa
GraphQL privato con token anti-CSRF e difese anti-bot pesanti (device check).
Uno scraper "puro" violerebbe i ToS e verrebbe bannato rapidamente.

Strategia adottata nel progetto:
  1. (default) Il marketplace è disabilitato; la UI lo mostra come
     "sperimentale" con una nota.
  2. Integrabile in seguito tramite Meta's ufficiale "oEmbed/graph" solo per
     pagine Business, oppure con un'estensione browser locale che l'utente
     esegue nella propria sessione autenticata (archiviazione solo dei dati
     visualizzati dall'utente stesso).

Questa classe è uno stub che rispetta il contratto BaseScraper così da poter
essere registrata nel registry senza rompere nulla.
"""
from __future__ import annotations

import logging

from bot.models import Listing, SearchParams
from bot.scraper.base import BaseScraper

log = logging.getLogger("bot.scraper.facebook")


class FacebookScraper(BaseScraper):
    name = "facebook"

    async def search(self, params: SearchParams) -> list[Listing]:
        log.warning(
            "[facebook] scraper non attivo: FB Marketplace richiede login e "
            "difende le API con token anti-bot. Vedi docstring e README."
        )
        return []
