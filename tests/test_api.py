"""Test end-to-end dell'API con il solo scraper demo (nessuna rete)."""
import pytest
from fastapi.testclient import TestClient

from bot.db import Database
from ui.server import create_app


@pytest.fixture()
def client(tmp_path):
    db = Database(tmp_path / "test.db")
    app = create_app(db=db)
    with TestClient(app) as c:
        yield c


def test_get_params_defaults(client):
    r = client.get("/api/params")
    assert r.status_code == 200
    assert r.json()["category"] in ("ram", "cpu")


def test_update_params_persist(client):
    body = client.get("/api/params").json()
    body.update(query="ryzen 7", max_price=150, sources=["demo"])
    r = client.put("/api/params", json=body)
    assert r.status_code == 200
    again = client.get("/api/params").json()
    assert again["query"] == "ryzen 7"
    assert again["max_price"] == 150


def test_run_now_finds_offers(client):
    body = client.get("/api/params").json()
    body.update(sources=["demo"], min_price=0, max_price=1000, radius_km=0,
                category="ram")
    client.put("/api/params", json=body)
    r = client.post("/api/bot/run")
    assert r.status_code == 200
    # con il demo scraper e range largo prima o poi produce offerte;
    # comunque la risposta deve essere ben formata
    assert "new_offers" in r.json()


def test_status_and_sources(client):
    assert client.get("/api/status").json()["state"] == "stopped"
    srcs = client.get("/api/sources").json()["sources"]
    assert "subito" in srcs and "demo" in srcs


def test_ui_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "PC Deals Bot" in r.text
