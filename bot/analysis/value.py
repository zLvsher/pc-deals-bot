"""Analisi di un annuncio: filtri utente + stima del 'prezzo equo'.

Due componenti:
  * `matches_params()`  → verifica rigorosa dei SearchParams (prezzo, parole
    incluse/escluse, spedizione/scambio a mano, distanza haversine).
  * `estimate_fair_price()` → euristica basata su specifiche estratte dal
    titolo (GB/MHz per la RAM, modello/socket e GHz-core per le CPU).
    E' volutamente semplice e regolabile: l'obiettivo è scartare il sovrapprezzo
    ed evidenziare i "colpo" (discount_pct alto), non essere un pricing engine.
"""
from __future__ import annotations

import math
import re

from bot.models import AnalyzedListing, Category, Listing, SearchParams, ShippingMode

# ------------------------------------------------------------------ distanza
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Piccola tab città->coordinate usata quando lo scraper non espone lat/lon.
CITY_COORDS: dict[str, tuple[float, float]] = {
    "milano": (45.464, 9.190), "torino": (45.070, 7.687),
    "roma": (41.902, 12.496), "bologna": (44.494, 11.343),
    "firenze": (43.770, 11.255), "verona": (45.438, 10.993),
    "padova": (45.406, 11.876), "napoli": (40.851, 14.268),
    "genova": (44.405, 8.946), "bari": (41.117, 16.872),
}


def _coords_for(listing: Listing) -> tuple[float, float] | None:
    if listing.lat is not None and listing.lon is not None:
        return listing.lat, listing.lon
    if listing.city:
        key = listing.city.lower().strip()
        for city, coords in CITY_COORDS.items():
            if city in key:
                return coords
    return None


# ------------------------------------------------------------------ parsing
_GB_RE = re.compile(r"(\d{1,3})\s*gb", re.I)
_MHZ_RE = re.compile(r"(\d{4})\s*mhz", re.I)
_DDR_RE = re.compile(r"ddr([345])", re.I)
_CPU_RE = re.compile(r"(i[3579]-\d{4}[a-z]{0,2}|ryzen\s*\d\s*\w{2,6})", re.I)
_STICKS_RE = re.compile(r"(\d)\s*x\s*(\d{1,3})\s*gb|(\d{1,3})\s*gb\s*[x-]\s*(\d{1,3})", re.I)


def parse_ram(title: str) -> dict:
    ddr = _DDR_RE.search(title)
    mhz = _MHZ_RE.search(title)
    # "2x16gb" / "16gb x 2" → totale moltiplicato, altrimenti il primo "\d+ gb"
    sm = _STICKS_RE.search(title)
    if sm:
        groups = [int(g) for g in sm.groups() if g]
        total_gb = groups[0] * groups[1] if len(groups) == 2 else groups[0]
    else:
        m = _GB_RE.search(title)
        total_gb = int(m.group(1)) if m else None
    return {"total_gb": total_gb, "ddr": int(ddr.group(1)) if ddr else None,
            "mhz": int(mhz.group(1)) if mhz else None}


# €/GB indicativi per l'usato (aggiornabili — fase successiva: prezzi storici)
PRICE_PER_GB = {3: 0.9, 4: 1.6, 5: 2.6}
MHz_BONUS = 0.004          # ogni MHz sopra 2400 vale ~0.4%/MHz... troncato
CPU_FAIR = {               # prezzo equo € per alcuni modelli diffusi (usato)
    "i3": 45, "i5": 105, "i7": 160, "i9": 240,
    "ryzen3": 55, "ryzen5": 95, "ryzen7": 150, "ryzen9": 230,
}


def estimate_fair_price(listing: Listing) -> tuple[float, float | None]:
    """Ritorna (prezzo_equo, perf_score). Fallback: ±25% sul prezzo richiesto."""
    title = f"{listing.title} {listing.raw_description}"
    if listing.category == Category.RAM:
        spec = parse_ram(title)
        gb = spec["total_gb"] or 16
        ddr = spec["ddr"] or 4
        base = PRICE_PER_GB[ddr] * gb
        if spec["mhz"]:
            ref = {3: 1600, 4: 2666, 5: 4800}[ddr]
            base *= max(0.85, min(1.35, 1 + (spec["mhz"] - ref) * MHz_BONUS / 10))
        return round(base, 2), float(spec["mhz"] or 0) or None
    # CPU
    m = _CPU_RE.search(title)
    fair = 120.0
    if m:
        token = m.group(1).lower().replace(" ", "")
        fam = token.split("-")[0] if "-" in token else re.match(r"ryzen\d", token)
        key = fam if isinstance(fam, str) else (fam.group(0) if fam else "")
        fair = CPU_FAIR.get(key.replace("core-", ""), 120.0)
    return fair, None


# ------------------------------------------------------------------ filtri
# Termini "deboli": da soli non identificano il prodotto (appaiono ovunque,
# anche negli annunci fuori-tema come interi PC gaming). Valgono come match
# solo se nel titolo è presente almeno un termine "forte" (marca/modello/capacità).
_WEAK_TERMS = {
    "ram", "cpu", "ddr", "gb", "ghz", "mhz", "pc",
    "kit", "banchi", "banco", "processore", "processor", "memoria",
    "memorie", "nuovo", "nuova", "usato", "per", "con", "di", "in", "ed", "e",
    "a", "o", "x",
}   # nota: "ddr3/4/5" NON sono deboli — distinguono davvero il prodotto
_GB_TOKEN_RE = re.compile(r"^\d{1,4}gb$")   # es. "16gb" → termine debole


def _query_tokens(query: str) -> list[str]:
    """Token della query, in minuscolo (ricerca case-insensitive)."""
    return [t for t in re.split(r"[^\w]+", query.lower()) if len(t) > 1]


def _is_weak(tok: str) -> bool:
    return tok in _WEAK_TERMS or _GB_TOKEN_RE.match(tok)


def relevance_score(listing: Listing, params: SearchParams) -> float:
    """Quota di token della query presenti nel testo dell'annuncio (0..1).

    Case-insensitive. I token deboli ("ram", "cpu", "16gb", …) contano come
    match solo se nel titolo è presente almeno un termine forte (marca,
    modello, DDRx): così un fuori-tema tipo "PC gaming con ram 16gb" per la
    query "ram ddr4 16gb Kingston" viene scartato, mentre "Kingston Fury
    16GB DDR4" passa anche scritto tutto in maiuscolo. Se la query contiene
    solo termini deboli ("ram ddr4"), il vincolo forte non si applica.
    """
    toks = _query_tokens(params.query)
    if not toks:
        return 1.0
    strong_q = [t for t in toks if not _is_weak(t)]
    title = listing.title.lower()
    text = f"{title} {listing.raw_description or ''}".lower()

    def _in(tok: str, hay: str) -> bool:
        # match su parola (evita falsi positivi tipo "ram" dentro "frame")
        return re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", hay) is not None

    if not strong_q:
        # query generica ("ram ddr4"): conta la presenza nel testo completo;
        # il termine debole "ram" è implicito se c'è un codice prodotto DDRx
        hit = sum(1 for t in toks if _in(t, text))
        if "ram" in toks and hit == len(toks) - 1 and re.search(r"ddr\d", text):
            hit += 1
        return hit / len(toks)

    # query specifica (marca/modello/DDRx): i token FORTI devono essere tutti
    # nel titolo — un fuori-tema (es. intero PC gaming) viene scartato.
    if not all(_in(t, title) for t in strong_q):
        return 0.0
    hit = len(strong_q)
    for t in toks:
        if _is_weak(t) and (_in(t, text) or (t == "ram" and re.search(r"ddr\d", text))):
            hit += 1
    return hit / len(toks)


def matches_params(listing: Listing, params: SearchParams) -> tuple[bool, str]:
    text = f"{listing.title} {listing.raw_description}".lower()

    # pertinenza alla ricerca (case-insensitive): il titolo deve contenere i
    # termini chiave della query — evita risultati fuori tema
    if relevance_score(listing, params) < params.min_relevance:
        return False, "titolo non pertinente alla ricerca"

    # prezzo
    if listing.price < 0:
        return False, "prezzo non indicato"
    if not (params.min_price <= listing.price <= params.max_price):
        return False, f"prezzo {listing.price:.0f}€ fuori range"

    # parole obbligatorie / escluse
    for w in params.required_words:
        if w.lower() not in text:
            return False, f"manca termine obbligatorio '{w}'"
    for w in params.exclude_words:
        if w.lower() in text:
            return False, f"contiene termine escluso '{w}'"

    # spedizione vs scambio a mano
    if params.shipping == ShippingMode.SHIP and not listing.shipping:
        return False, "nessuna spedizione"
    if params.shipping == ShippingMode.HAND and listing.shipping:
        # se spedisce può comunque fare scambio a mano: scartiamo solo se
        # il testo dice chiaramente "solo spedizione"
        if "solo spedizione" in text:
            return False, "solo spedizione, no scambio a mano"

    # distanza
    # distanza: scarta solo se CONOSCIAMO la posizione e supera il raggio.
    # (posizione sconosciuta → tiene: meglio un falso positivo che zero risultati)
    if params.radius_km > 0:
        coords = _coords_for(listing)
        if coords is not None:
            dist = haversine_km(params.latitude, params.longitude, *coords)
            if dist > params.radius_km:
                return False, f"a {dist:.0f} km (> {params.radius_km:.0f})"

    return True, ""


def analyze(listing: Listing, params: SearchParams) -> AnalyzedListing:
    ok, reason = matches_params(listing, params)
    fair, perf = estimate_fair_price(listing)
    discount = (fair - listing.price) / fair * 100 if fair > 0 and listing.price >= 0 else 0.0
    return AnalyzedListing(
        listing=listing,
        fair_price=round(fair, 2),
        discount_pct=round(discount, 1),
        matches_filters=ok,
        reason=reason,
        perf_score=perf,
    )
