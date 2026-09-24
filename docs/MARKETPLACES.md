# Analisi dei marketplace (study log)

> Documento vivo: ogni volta che uno scraper si rompe, aggiornare qui note e fix.

## Tabella riassuntiva

| Sito | Tecnica di accesso | Filtro prezzo nativo | Info spedizione | Geolocalizzazione | Anti-bot | Stato |
|---|---|---|---|---|---|---|
| **Subito.it** | HTML SSR (`article[data-id]`) | ✅ `&pz=min-max` | solo nel testo/tag | provincia/comune, niente lat/lon | media (UA + rate limit) | ✅ implementato |
| **Vinted** | API JSON interna `/api/v2/catalog` | ✅ `price_from/to` (centesimi) | ✅ `can_be_sent` | città del venditore | alta (rate limit forte) | ✅ implementato |
| **Wallapop** | JSON embedded `__NEXT_DATA__` | parzialmente via URL | campo `shipping` | ✅ lat/lon reali | media | ✅ implementato |
| **FB Marketplace** | richiede login + GraphQL protetto | — | — | — | altissima | ⚠️ stub (vedi sotto) |
| **eBay.it** (extra) | API ufficiale con chiave | ✅ | ✅ | CAP | nessuna | 💡 candidato fase 2 |

## Comportamenti osservati e scelte di design

### Subito.it
- SERP in HTML classico: nessun browser headless necessario.
- Parametri URL utili: `q` (testo), `pz` (prezzo min-max), `fk=3` (recenti),
  `comune=` per restringere l'area. La distanza reale non esiste → risolviamo
  la città dell'annuncio con tabella `CITY_COORDS` + haversine nel modulo analysis.
- "Spedizione" è talvolta un badge nell'articolo, talvolta solo nel testo:
  doppio controllo.
- Rischio: cambio markup → i test parser (`tests/test_scrapers.py`) con HTML
  fixture ci avvisano subito.

### Vinted
- SPA + API interna `GET /api/v2/catalog?search_text=...` → JSON pulito.
  Serve warm-up della sessione (cookie dalla homepage) e header
  `X-Requested-With`. Prezzo in centesimi.
- Catalogo hardware limitato ma ottimo per kit RAM "svenduti".
- Rate limit aggressivo: delay 3–7s tra richieste, una pagina per ciclo.

### Wallapop
- Next.js: parsiamo `__NEXT_DATA__` invece del GraphQL interno (gli hash delle
  query cambiano spesso). Unico sito che espone **lat/lon** → filtro raggio preciso.

### Facebook Marketplace
- Non accessibile senza login; scraping diretto = ban rapido + violazione ToS.
- Decisione: stub registrato ma disabilitato; eventuale integrazione futura con
  estensione browser locale che esegue nella sessione dell'utente.

## Regole anti-ban trasversali (implementate in `BaseScraper`)
1. User-Agent desktop realistico + `Accept-Language: it-IT`.
2. Throttle randomizzato per sito (1.5–4s, Vinted 3–7s).
3. Una richiesta per marketplace per ciclo di scansione (niente paginazione selvaggia).
4. Su 403/429: log con suggerimento, nessun retry immediato (evita escalation).
5. Cache/deduplica lato nostro: mai riverificare lo stesso annuncio.

## Definizione di "offerta vantaggiosa"
Annuncio che passa TUTTI i filtri utente E ha sconto ≥10% rispetto al
prezzo equo stimato (`bot/analysis/value.py`). Le soglie sono configurabili
nel codice; in fase 2 diventano parametri modificabili dalla GUI.
