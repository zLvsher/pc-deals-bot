"""Stub del notifier Telegram (fase 2). Interfaccia stabile già usata dal bot."""
from __future__ import annotations

import logging
import os

log = logging.getLogger("bot.notify")


class Notifier:
    """Invia le nuove offerte. Oggi: log + WebSocket (a cura del caller).

    Per abilitare Telegram:
        export TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...
    e installare python-telegram-bot (già in requirements.txt).
    """

    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            log.info("Telegram non configurato: notifiche solo via UI.")

    async def send_offer(self, title: str, price: float, url: str) -> None:
        msg = f"🔥 Offerta: {title} — {price:.0f}€ — {url}"
        log.info(msg)
        if not self.enabled:
            return
        try:  # pragma: no cover - rete esterna
            import httpx

            api = f"https://api.telegram.org/bot{self.token}/sendMessage"
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(api, json={"chat_id": self.chat_id, "text": msg})
        except Exception as exc:  # noqa: BLE001
            log.error("invio telegram fallito: %s", exc)
