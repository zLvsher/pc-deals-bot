// Logica della GUI: carica i parametri dal backend, li salva, mostra le offerte.
const $ = (id) => document.getElementById(id);

const api = {
  get: (p) => fetch(p).then(r => r.json()),
  put: (p, b) => fetch(p, { method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(b) }).then(r => r.json()),
  post: (p) => fetch(p, { method: "POST" }).then(r => r.json()),
};

let currentSources = [];

// ------------------------------------------------------------- parametri
async function loadParams() {
  const p = await api.get("/api/params");
  $("query").value = p.query;
  $("min_relevance").value = p.min_relevance ?? 0.6;
  $("relevance-out").textContent = `${Math.round((p.min_relevance ?? 0.6) * 100)}%`;
  $("category").value = p.category;
  $("min_price").value = p.min_price;
  $("max_price").value = p.max_price;
  $("shipping").value = p.shipping;
  $("required_words").value = (p.required_words || []).join(", ");
  $("exclude_words").value = (p.exclude_words || []).join(", ");
  $("latitude").value = p.latitude;
  $("longitude").value = p.longitude;
  $("radius_km").value = p.radius_km;
  $("radius-out").textContent = p.radius_km == 0 ? "tutta Italia" : `${p.radius_km} km`;
  $("interval_minutes").value = p.interval_minutes;

  const { sources } = await api.get("/api/sources");
  currentSources = sources;
  const box = $("sources-box");
  box.querySelectorAll("label").forEach(e => e.remove());
  for (const s of sources) {
    const lab = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = s;
    cb.checked = p.sources.includes(s);
    lab.append(cb, document.createTextNode(s + (s === "facebook" ? " (sperimentale)" : "")));
    box.append(lab);
  }
}

$("radius_km").addEventListener("input", e => {
  $("radius-out").textContent = e.target.value == 0 ? "tutta Italia" : `${e.target.value} km`;
});

$("min_relevance").addEventListener("input", e => {
  $("relevance-out").textContent = `${Math.round(e.target.value * 100)}%`;
});

$("btn-geo").addEventListener("click", () => {
  if (!navigator.geolocation) return alert("Geolocalizzazione non supportata.");
  navigator.geolocation.getCurrentPosition(
    pos => { $("latitude").value = pos.coords.latitude.toFixed(4);
             $("longitude").value = pos.coords.longitude.toFixed(4); },
    err => alert("Impossibile ottenere la posizione: " + err.message));
});

$("params-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const cur = await api.get("/api/params");
  const body = {
    ...cur,
    query: $("query").value.trim(),
    min_relevance: parseFloat($("min_relevance").value),
    category: $("category").value,
    min_price: parseFloat($("min_price").value || 0),
    max_price: parseFloat($("max_price").value || 1000),
    shipping: $("shipping").value,
    required_words: $("required_words").value.split(",").map(s => s.trim()).filter(Boolean),
    exclude_words: $("exclude_words").value.split(",").map(s => s.trim()).filter(Boolean),
    latitude: parseFloat($("latitude").value),
    longitude: parseFloat($("longitude").value),
    radius_km: parseFloat($("radius_km").value),
    interval_minutes: parseInt($("interval_minutes").value || 15),
    sources: [...document.querySelectorAll("#sources-box input:checked")].map(i => i.value),
  };
  await api.put("/api/params", body);
  flashSaved();
});

function flashSaved() {
  $("save-msg").textContent = "salvato ✓";
  setTimeout(() => $("save-msg").textContent = "", 2500);
}

// ------------------------------------------------------------- controlli bot
$("btn-start").onclick = async () => { await api.post("/api/bot/start"); refreshStatus(); };
$("btn-stop").onclick  = async () => { await api.post("/api/bot/stop");  refreshStatus(); };
$("btn-run").onclick   = async () => {
  $("btn-run").disabled = true; $("btn-run").textContent = "...";
  const res = await api.post("/api/bot/run");
  (res.new_offers || []).forEach(addOffer);
  $("btn-run").disabled = false; $("btn-run").textContent = "⚡ Scansiona ora";
  refreshStatus();
};

async function refreshStatus() {
  const s = await api.get("/api/status");
  const dot = $("state-dot");
  dot.className = "dot " + (s.state === "running" ? "running" : "stopped");
  $("state-text").textContent = s.state === "running" ? "in esecuzione" : "fermo";
  $("last-run").textContent = s.last_run
    ? `· ultima scansione: ${new Date(s.last_run + "Z").toLocaleTimeString()} · viste ${s.listings_seen} · offerte ${s.offers_found}`
    : "";
}

// ------------------------------------------------------------- offerte
let listCleared = false;   // true dopo "Pulisci": blocca il re-render dello storico

function addOffer(o, fromHistory = false) {
  if (fromHistory && listCleared) return;  // non ri-aggiungere ciò che l'utente ha pulito
  const l = o.listing;
  const li = document.createElement("li");
  li.className = "offer";
  const fair = (typeof o.fair_price === "number") ? o.fair_price.toFixed(0) : o.fair_price;
  const disc = (typeof o.discount_pct === "number") ? o.discount_pct.toFixed(0) : o.discount_pct;
  li.innerHTML = `
    <a href="${l.url}" target="_blank" rel="noopener">${l.title}</a>
    <div class="meta">
      <span class="price">${Number(l.price).toFixed(0)} €</span>
      <span class="deal">-${disc}% vs prezzo equo (${fair}€)</span>
      <span>📦 ${l.shipping ? "spedizione" : "scambio a mano"}</span>
      <span>📍 ${l.city || "?"}</span>
      <span>da ${l.source}</span>
    </div>`;
  $("offers-list").prepend(li);
  bumpCount(1);
}

function bumpCount(n) {
  const el = $("offers-count");
  el.textContent = parseInt(el.textContent || "0", 10) + n;
}

// ----------------------------------------------------- pulisci risultati
$("btn-clear").addEventListener("click", () => {
  $("offers-list").innerHTML = "";
  $("offers-count").textContent = "0";
  listCleared = true;   // lo storico non viene ri-aggiunto finché non ricarichi la pagina
});

async function loadHistory() {
  const { offers } = await api.get("/api/offers");
  // gli item dello storico sono Listing "piatti": li riavvolgo in AnalyzedListing-lite
  offers.slice().reverse().forEach(l =>
    addOffer({ listing: l, discount_pct: 0, fair_price: l.price }, true));
}

// ------------------------------------------------------------- WebSocket push
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "new_offer") addOffer(msg.data);
  };
  ws.onclose = () => setTimeout(connectWS, 3000);  // reconnect
}

loadParams();
loadHistory();
refreshStatus();
setInterval(refreshStatus, 15000);
connectWS();
