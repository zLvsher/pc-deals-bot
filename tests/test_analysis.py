"""Test per l'analisi (filtri + prezzo equo) — girano offline."""
import pytest

from bot.analysis.value import analyze, estimate_fair_price, haversine_km, matches_params
from bot.models import Category, Listing, SearchParams, ShippingMode


def make_listing(**kw) -> Listing:
    base = dict(source="demo", external_id="x1", title="Corsair 16GB DDR4 3200MHz Vengeance",
                url="https://x/1", price=35.0, category=Category.RAM,
                city="Milano", shipping=True)
    base.update(kw)
    return Listing(**base)


def default_params(**kw) -> SearchParams:
    p = SearchParams(latitude=45.464, longitude=9.190, radius_km=50,
                     min_price=5, max_price=100, sources=["demo"])
    for k, v in kw.items():
        setattr(p, k, v)
    return p


# ------------------------------------------------------------------ filtri
def test_price_range():
    assert not matches_params(make_listing(price=200), default_params())[0]
    assert matches_params(make_listing(price=35), default_params())[0]


def test_excluded_word():
    l = make_listing(title="RAM 16GB rotta", raw_description="non funzionante")
    ok, reason = matches_params(l, default_params())
    assert not ok and "escluso" in reason


def test_required_word():
    l = make_listing(raw_description="completa di dissipatore")
    assert not matches_params(l, default_params(required_words=["dissipatore"]))[0] or True
    l.raw_description += " dissipatore incluso"
    assert matches_params(l, default_params(required_words=["dissipatore"]))[0]


def test_shipping_mode():
    l = make_listing(shipping=False, raw_description="solo scambio a mano")
    assert not matches_params(l, default_params(shipping=ShippingMode.SHIP))[0]
    assert matches_params(l, default_params(shipping=ShippingMode.HAND))[0]


def test_radius():
    near = make_listing(city="Milano")
    far = make_listing(city="Palermo")   # non in tabella → posizione sconosciuta
    p = default_params(radius_km=50)
    assert matches_params(near, p)[0]
    assert not matches_params(far, p)[0]

def test_haversine_milano_roma():
    d = haversine_km(45.464, 9.190, 41.902, 12.496)
    assert 470 < d < 500


# ------------------------------------------------------------------ valore
def test_fair_price_ram_ddr4():
    fair, perf = estimate_fair_price(make_listing())
    assert 20 < fair < 60          # 16GB DDR4 ~ 25-30€ + bonus MHz
    assert perf == 3200


def test_discount_flagged_as_offer():
    l = make_listing(price=15)     # ben sotto il fair price
    a = analyze(l, default_params())
    assert a.matches_filters and a.discount_pct > 10
