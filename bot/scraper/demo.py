"""Demo scraper: genera annunci finti ma realistici.

Serve a far funzionare end-to-end l'intera pipeline (bot → analisi → API →
UI → WebSocket) senza dipendere dalla rete e senza rischi di ban durante lo
sviluppo. In produzione si disabilita togliendo "demo" dai `sources`.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from bot.models import Category, Listing, SearchParams
from bot.scraper.base import BaseScraper

RAM_MODELS = [
    ("Kingston Fury Beast 16GB DDR4 3200MHz", 38, 55),
    ("Corsair Vengeance LPX 2x16GB DDR4 3600MHz", 60, 90),
    ("G.Skill Trident Z5 32GB DDR5 6000MHz", 95, 140),
    ("Samsung 8GB DDR4 2666MHz (usato)", 12, 20),
    ("Crucial 16GB DDR5 4800MHz", 40, 60),
]
CPU_MODELS = [
    ("Intel Core i5-12400F", 90, 120),
    ("AMD Ryzen 5 5600X", 80, 110),
    ("AMD Ryzen 7 5800X3D", 130, 175),
    ("Intel Core i7-9700K", 95, 130),
    ("AMD Ryzen 5 3600", 45, 70),
]
CITIES = ["Milano", "Bologna", "Torino", "Roma", "Verona", "Padova", "Firenze"]


class DemoScraper(BaseScraper):
    name = "demo"
    min_delay = 0.0
    max_delay = 0.0

    async def search(self, params: SearchParams) -> list[Listing]:
        pool = RAM_MODELS if params.category == Category.RAM else CPU_MODELS
        n = random.randint(4, 8)
        out: list[Listing] = []
        for i in range(n):
            title, lo, hi = random.choice(pool)
            # prezzo reale random, talvolta sotto il "fair price" → offerta!
            price = round(random.uniform(lo * 0.55, hi * 1.15), 0)
            ext_id = f"{title[:12]}-{datetime.utcnow():%Y%m%d%H%M%S}-{i}"
            city = random.choice(CITIES)
            out.append(self.make_listing(
                external_id=ext_id,
                title=title,
                url=f"https://esempio.it/annuncio/{abs(hash(ext_id))}",
                price=float(price),
                category=params.category,
                city=city,
                shipping=random.random() < 0.6,
                description=f"{title} - {city} - usato funzionante",
            ))
        return out
