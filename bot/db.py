"""Persistenza SQLite: annunci già visti (deduplica), parametri, storico offerte."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from bot.models import SearchParams

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "offers.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_listings (
    uid         TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    price       REAL NOT NULL,
    data_json   TEXT NOT NULL,
    is_offer    INTEGER NOT NULL DEFAULT 0,
    first_seen  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS settings (
    id      INTEGER PRIMARY KEY CHECK (id = 1),
    params_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_seen_source ON seen_listings(source);
"""


class Database:
    """Wrapper thread-safe minimale su sqlite3 (usato sia dal bot sia dalla API)."""

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---------------------------------------------------------- deduplica
    def is_seen(self, uid: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM seen_listings WHERE uid = ?", (uid,)
            ).fetchone()
        return row is not None

    def mark_seen(self, uid: str, listing_dict: dict, is_offer: bool) -> None:
        """Inserisce o AGGIORNA l'annuncio. Se era già offerto e ora non lo è
        più (prezzo cambiato), il flag viene aggiornato di conseguenza."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO seen_listings
                   (uid, source, title, url, price, data_json, is_offer)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(uid) DO UPDATE SET
                     price = excluded.price,
                     data_json = excluded.data_json,
                     is_offer = excluded.is_offer""",
                (
                    uid,
                    listing_dict["source"],
                    listing_dict["title"],
                    listing_dict["url"],
                    listing_dict["price"],
                    json.dumps(listing_dict, ensure_ascii=False, default=str),
                    int(is_offer),
                ),
            )
            self._conn.commit()

    # ---------------------------------------------------------- offerte
    def get_offers(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT data_json FROM seen_listings
                   WHERE is_offer = 1 ORDER BY first_seen DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [json.loads(r["data_json"]) for r in rows]

    def count_stats(self) -> tuple[int, int]:
        with self._lock:
            seen = self._conn.execute("SELECT COUNT(*) FROM seen_listings").fetchone()[0]
            offers = self._conn.execute(
                "SELECT COUNT(*) FROM seen_listings WHERE is_offer=1"
            ).fetchone()[0]
        return seen, offers

    # ---------------------------------------------------------- parametri
    def save_params(self, params: SearchParams) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO settings (id, params_json) VALUES (1, ?)
                   ON CONFLICT(id) DO UPDATE SET params_json = excluded.params_json""",
                (params.model_dump_json(),),
            )
            self._conn.commit()

    def load_params(self) -> Optional[SearchParams]:
        with self._lock:
            row = self._conn.execute(
                "SELECT params_json FROM settings WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        try:
            return SearchParams.model_validate_json(row["params_json"])
        except Exception:
            return None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
