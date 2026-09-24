"""Modelli condivisi: annunci, parametri di ricerca, risultati dell'analisi."""
from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    RAM = "ram"
    CPU = "cpu"


class ShippingMode(str, Enum):
    ANY = "any"              # indifferente
    SHIP = "ship"            # solo con spedizione
    HAND = "hand"            # solo scambio a mano / ritiro


class SortOrder(str, Enum):
    NEWEST = "newest"        # più recenti (default per un bot di offerte)
    PRICE_ASC = "price_asc"  # prezzo crescente
    VALUE_DESC = "value_desc"  # miglior rapporto €/perf


class Listing(BaseModel):
    """Annuncio normalizzato, indipendente dal marketplace di origine."""

    source: str                          # es. "subito", "vinted", ...
    external_id: str                     # id originale sul sito
    title: str
    url: str
    price: float                         # in euro (-1 se "gratis/da concordare")
    currency: str = "EUR"
    category: Category = Category.RAM
    city: Optional[str] = None
    lat: Optional[float] = None          # se il sito la espone
    lon: Optional[float] = None
    shipping: bool = False               # true se il venditore spedisce
    created_at: Optional[datetime] = None
    raw_description: str = ""
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def uid(self) -> str:
        """Identificativo globale univoco per deduplica."""
        return hashlib.sha1(f"{self.source}:{self.external_id}".encode()).hexdigest()


class SearchParams(BaseModel):
    """Parametri modificabili dall'utente dalla GUI."""

    query: str = "ram ddr4"                      # oggetto da cercare
    category: Category = Category.RAM
    min_price: float = Field(0, ge=0)
    max_price: float = Field(200, gt=0)
    shipping: ShippingMode = ShippingMode.ANY    # spedizione / scambio a mano
    exclude_words: list[str] = Field(
        default_factory=lambda: ["rotto", "guasto", "non funzionante", "per parti"]
    )                                            # termini ESCLUSI
    required_words: list[str] = Field(default_factory=list)  # termini INCLUSI obbligatori
    latitude: float = Field(45.464, description="Latitudine utente (Milano default)")
    longitude: float = Field(9.190, description="Longitudine utente")
    radius_km: float = Field(50, ge=0, description="0 = nessuna restrizione")
    sources: list[str] = Field(
        default_factory=lambda: ["demo"],
        description="Marketplace abilitati: subito, vinted, wallapop, facebook, demo",
    )
    interval_minutes: int = Field(15, ge=1, description="Ogni quanto gira il bot")
    sort: SortOrder = SortOrder.NEWEST
    enabled: bool = True


class AnalyzedListing(BaseModel):
    """Annuncio + esito dell'analisi valore (prezzo equo stimato)."""

    listing: Listing
    fair_price: float                    # stima di mercato onesta
    discount_pct: float                  # sconto rispetto al prezzo equo
    matches_filters: bool                # rispetta i SearchParams correnti
    reason: str = ""                     # perché è stato scartato (debug/UI)
    perf_score: Optional[float] = None   # MHz DDR o GHz CPU, per il rapporto €/perf


class BotStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class StatusInfo(BaseModel):
    state: BotStatus = BotStatus.STOPPED
    last_run: Optional[datetime] = None
    listings_seen: int = 0
    offers_found: int = 0
    next_run: Optional[datetime] = None
    message: str = ""
