# 🖥️ PC Deals Bot

Bot che monitora i marketplace dell'usato italiani (**Subito, Vinted, Wallapop,
…**) e segnala in tempo reale le offerte vantaggiose su **RAM e CPU**, con una
**GUI web locale** per configurare tutti i parametri di ricerca.

> ⚠️ Uso personale: rispetta i ToS dei siti, mantieni bassi gli intervalli di
> scansione e non rivendi i dati raccolti.

---

## 1. Perché Python

| Criterio | Motivo |
|---|---|
| **Ecosistema scraping maturo** | `httpx` (async), `BeautifulSoup`, `Playwright` come fallback |
| **Sviluppo rapido** | tipizzazione con Pydantic → i modelli validano anche la API della GUI |
| **Backend + GUI insieme** | FastAPI serve API REST, WebSocket e file statici da un solo processo |
| **Deploy facile** | `python run.py` ovunque; packaging futuro con PyInstaller |
| **Manutenibilità** | aggiungere un marketplace = una classe di ~60 righe |

## 2. Architettura

```
┌─────────────────────────── GUI browser (static/) ───────────────────────┐
│  parametri di ricerca · avvia/ferma · offerte live (WebSocket) · GPS    │
└──────────────▲──────────────────────────────────────────▲───────────────┘
               │ REST /api/*                              │ WS /ws
┌──────────────┴──────────────────────────────────────────┴───────────────┐
│                        ui/server.py (FastAPI)                           │
├─────────────────────────────────────────────────────────────────────────┤
│  bot/core.py — OfferSearchBot + APScheduler (loop ogni N minuti)        │
│     ├─ bot/scraper/*  → subito · vinted · wallapop · facebook(stub)     │
│     │                    + demo (offline per sviluppo/test)             │
│     ├─ bot/analysis/value.py → filtri utente + prezzo equo stimato      │
│     ├─ bot/db.py (SQLite) → deduplica annunci, storico, parametri       │
│     └─ bot/notify/telegram.py → alert (fase 2, già cablato)             │
└─────────────────────────────────────────────────────────────────────────┘
```

Flusso di una scansione:
`params → scraper paralleli → normalizzazione Listing → deduplica DB →
analisi (filtri + sconto vs prezzo equo) → offerta? → salva + push WebSocket
(+ Telegram se configurato)`.

### Parametri configurabili dalla GUI
- oggetto da cercare (testo libero) e categoria RAM/CPU
- prezzo min/max
- spedizione **o** scambio a mano
- termini **inclusi** e **esclusi** (es. scarta "rotto", "non funzionante")
- posizione (con pulsante GPS del browser) + **raggio in km**
- quali marketplace interrogare
- intervallo di scansione del bot

Lo studio dettagliato del comportamento dei singoli siti (formato risposte,
filtri nativi, anti-bot, scelte tecniche) è in **[docs/MARKETPLACES.md](docs/MARKETPLACES.md)**.

## 3. Installazione e avvio

```bash
git clone https://github.com/<tuo-utente>/pc-deals-bot.git
cd pc-deals-bot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py            # → apri http://127.0.0.1:8000
```

All'avvio trovi spuntato lo scraper **demo**: premi **⚡ Scansiona ora** per
vedere la pipeline funzionare senza toccare i siti reali. Per la ricerca vera
spunta *subito* (e via via gli altri) e salva i parametri.

Test (offline):

```bash
pytest -q
```

Notifiche Telegram (opzionali):

```bash
export TELEGRAM_BOT_TOKEN="..."   # crea il bot con @BotFather
export TELEGRAM_CHAT_ID="..."
```

## 4. Roadmap

- [ ] Soglia "sconto minimo" e sorting €/perf nella GUI
- [ ] Prezzi storici per modello (grafico fair-price dinamico)
- [ ] Fallback Playwright per i siti che alzano Cloudflare
- [ ] Estensione browser per Facebook Marketplace (sessione utente)
- [ ] eBay.it via API ufficiale
- [ ] Packaging desktop (PyInstaller) e Tauri wrapper della UI
- [ ] Multi-profilo di ricerca (più query contemporanee)

## 5. Licenza

MIT — vedi [LICENSE](LICENSE).
