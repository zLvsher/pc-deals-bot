"""API REST + WebSocket (FastAPI).

Endpoint principali:
  GET  /                   → UI statica
  GET  /api/params         → parametri correnti
  PUT  /api/params         → aggiorna i parametri (la GUI li modifica qui)
  POST /api/bot/start      → avvia il loop periodico
  POST /api/bot/stop       → ferma il loop
  POST /api/bot/run        → scansione immediata (una tantum)
  GET  /api/status         → stato del bot
  GET  /api/offers         → storico offerte trovate
  WS   /ws                 → push in tempo reale delle nuove offerte
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bot.core import OfferSearchBot
from bot.db import Database
from bot.models import AnalyzedListing, SearchParams

log = logging.getLogger("bot.api")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class WSManager:
    """Gestisce i client WebSocket connessi alla UI."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    def broadcast_from_sync_thread(self, payload: dict) -> None:
        """Chiamata dal bot (callback sincrona): schedula l'invio sull'event loop."""
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)

    async def _broadcast(self, payload: dict) -> None:
        dead = []
        msg = json.dumps(payload, ensure_ascii=False, default=str)
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


def create_app(db: Database | None = None) -> FastAPI:
    database = db or Database()
    manager = WSManager()

    def on_offer(analyzed: AnalyzedListing) -> None:
        manager.broadcast_from_sync_thread(
            {"type": "new_offer", "data": analyzed.model_dump(mode="json")}
        )

    bot = OfferSearchBot(database, on_offer=on_offer)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager.loop = asyncio.get_running_loop()
        yield
        await bot.shutdown()

    app = FastAPI(title="PC Deals Bot", version="0.1.0", lifespan=lifespan)
    app.state.bot = bot
    app.state.db = database

    # ------------------------------------------------------------------ UI
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    # -------------------------------------------------------------- API bot
    @app.get("/api/params")
    async def get_params() -> dict:
        return bot.params.model_dump(mode="json")

    @app.put("/api/params")
    async def put_params(params: SearchParams) -> dict:
        bot.update_params(params)
        return {"ok": True, "params": params.model_dump(mode="json")}

    @app.post("/api/bot/start")
    async def start_bot() -> dict:
        bot.start()
        return {"ok": True}

    @app.post("/api/bot/stop")
    async def stop_bot() -> dict:
        bot.stop()
        return {"ok": True}

    @app.post("/api/bot/run")
    async def run_now() -> dict:
        offers = await bot.run_once()
        return {
            "ok": True,
            "new_offers": [o.model_dump(mode="json") for o in offers],
        }

    @app.get("/api/status")
    async def status() -> dict:
        return bot.get_status().model_dump(mode="json")

    @app.get("/api/offers")
    async def offers(limit: int = 200) -> dict:
        return {"offers": database.get_offers(limit)}

    @app.get("/api/sources")
    async def sources() -> dict:
        from bot.scraper import available_sources
        return {"sources": available_sources()}

    # ------------------------------------------------------------ WebSocket
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        try:
            while True:
                await ws.receive_text()   # keepalive / comandi futuri
        except WebSocketDisconnect:
            manager.disconnect(ws)

    return app


# per `uvicorn ui.server:app`
app = create_app()
