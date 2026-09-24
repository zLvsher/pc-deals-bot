"""OfferSearchBot — il cuore dell'applicazione.

Gira con APScheduler ogni `interval_minutes`:
  1. legge i SearchParams correnti (modificabili live dalla GUI);
  2. lancia in parallelo gli scraper dei marketplace abilitati;
  3. deduplica con SQLite (uid = source:external_id);
  4. analizza ogni annuncio (filtri + prezzo equo);
  5. se è un'offerta → la salva, la notifica (Telegram se attivo) e la
     pubblica sulla coda interna che la UI consuma via WebSocket.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.analysis.value import analyze
from bot.db import Database
from bot.models import AnalyzedListing, BotStatus, SearchParams, StatusInfo
from bot.notify.telegram import Notifier
from bot.scraper import build_scrapers

log = logging.getLogger("bot.core")


class OfferSearchBot:
    def __init__(self, db: Database,
                 on_offer: Optional[Callable[[AnalyzedListing], None]] = None) -> None:
        self.db = db
        self.params: SearchParams = db.load_params() or SearchParams()
        self.notifier = Notifier()
        self.on_offer = on_offer            # callback verso la UI (WebSocket)
        self._scheduler = AsyncIOScheduler()
        self._job = None
        self.status = StatusInfo()
        self.total_offers_this_session = 0

    # ------------------------------------------------------------ ciclo
    async def run_once(self) -> list[AnalyzedListing]:
        """Una passata completa di scansione. Ritorna le NUOVE offerte."""
        params = self.params
        scrapers = build_scrapers(params.sources)
        results = await asyncio.gather(
            *(s.search(params) for s in scrapers), return_exceptions=True
        )
        new_offers: list[AnalyzedListing] = []
        seen_count = 0
        for res in results:
            if isinstance(res, Exception):
                log.error("scraper fallito: %s", res)
                continue
            for listing in res:
                seen_count += 1
                analyzed = analyze(listing, params)
                is_offer = analyzed.matches_filters and analyzed.discount_pct >= 10
                already = self.db.is_seen(listing.uid)
                self.db.mark_seen(listing.uid,
                                  listing.model_dump(mode="json"), is_offer)
                if not is_offer or already:
                    continue
                new_offers.append(analyzed)
                self.total_offers_this_session += 1
                # 1) NOTIFICA PRIMA alla GUI (WebSocket): non deve dipendere
                #    da Telegram/rete esterna che può bloccare l'intero ciclo.
                if self.on_offer:
                    try:
                        self.on_offer(analyzed)
                    except Exception:  # noqa: BLE001
                        log.exception("callback UI fallita")
                # 2) poi alert esterno (Telegram) in modo best-effort
                try:
                    await asyncio.wait_for(
                        self.notifier.send_offer(
                            listing.title, listing.price, listing.url),
                        timeout=5)
                except Exception as exc:  # noqa: BLE001
                    log.debug("notifica telegram saltata: %s", exc)
        self.status.last_run = datetime.utcnow()
        seen_total, offers_total = self.db.count_stats()
        self.status.listings_seen = seen_total
        self.status.offers_found = offers_total
        self.status.message = (
            f"{seen_count} annunci controllati, {len(new_offers)} nuove offerte"
        )
        log.info("[run] %s", self.status.message)
        return new_offers

    # ------------------------------------------------------------ start/stop
    def start(self) -> None:
        if self.status.state == BotStatus.RUNNING:
            return
        self._ensure_scheduler()
        minutes = max(1, self.params.interval_minutes)
        self._job = self._scheduler.add_job(
            self.run_once, "interval", minutes=minutes, id="scan",
            replace_existing=True, next_run_time=datetime.now(),
        )
        self.status.state = BotStatus.RUNNING
        self.status.next_run = datetime.utcnow()
        log.info("bot avviato (intervallo %d min)", minutes)

    def stop(self) -> None:
        if self._job:
            self._job.remove()
            self._job = None
        self.status.state = BotStatus.STOPPED
        log.info("bot fermato")

    def update_params(self, params: SearchParams) -> None:
        """Cambio parametri live dalla GUI: persiste + ri-programma il job."""
        self.params = params
        self.db.save_params(params)
        if self.status.state == BotStatus.RUNNING:
            self.stop()
            self.start()

    def _ensure_scheduler(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()

    def get_status(self) -> StatusInfo:
        job = self._scheduler.get_job("scan") if self._scheduler.running else None
        if job and job.next_run_time:
            self.status.next_run = job.next_run_time.replace(tzinfo=None)
        return self.status

    async def shutdown(self) -> None:
        self.stop()
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
