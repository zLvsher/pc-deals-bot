"""Test dei parser degli scraper (offline, su HTML/JSON catturati)."""
from bot.models import Category, SearchParams
from bot.scraper.subito import SubitoScraper
from bot.scraper.vinted import VintedScraper
from bot.scraper.wallapop import WallapopScraper

SUBITO_HTML = """
<html><body>
<article data-id="123456789">
  <h2><a class="plink" href="//offerta/milano/hardware/l-Kingston-Fury-16GB-DDR4-3200_d_123456789.htm">Kingston Fury 16GB DDR4 3200MHz</a></h2>
  <p class="price">35 €</p>
  <p class="location-txt">Milano</p>
  <p>Disponibile la spedizione in tutto il territorio</p>
</article>
<article data-id="987654321">
  <h2><a class="plink" href="/offerta/roma/cpu/Ryzen-5-5600X_d_987654321.htm">AMD Ryzen 5 5600X</a></h2>
  <p class="price">80 €</p>
  <p class="location-txt">Roma</p>
  <p>scambio a mano zona centro</p>
</article>
</body></html>
"""


def test_subito_parser():
    s = SubitoScraper()
    items = s.parse_listings(SUBITO_HTML, Category.RAM)
    assert len(items) == 2
    first = items[0]
    assert first.price == 35.0
    assert first.shipping is True
    assert first.city == "Milano"
    assert first.url.startswith("https://www.subito.it/")
    assert items[1].shipping is False


VINTED_JSON = {
    "items": [
        {"item": {"id": 111, "title": "RAM Corsair 2x8GB DDR4", "price": 4500,
                  "can_be_sent": True, "urls": {"web": "ram-corsair"},
                  "description": "ottime"},
         "user": {"city": "Torino"}},
        {"item": {"id": 222, "title": "CPU Intel i5 8400", "price": 9000,
                  "can_be_sent": False, "urls": {}},
         "user": {}},
    ]
}


def test_vinted_parser():
    s = VintedScraper()
    items = s.parse_items(VINTED_JSON, Category.CPU)
    assert len(items) == 2
    assert items[0].price == 45.0          # centesimi → euro
    assert items[0].shipping is True
    assert "catalog/111" in items[0].url


WALLAPOOPO_HTML = """
<html><head>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"initialState":{"search":{"items":[
  {"product":{"id":"abc1","title":"G.Skill 32GB DDR5 6000","price":{"amount":105},
    "location":{"lat":45.46,"lon":9.19,"address":"Milano"},"shipping":true,
    "description":"perfetta"}}
]}}}}
</script></head><body></body></html>
"""


def test_wallapop_parser():
    s = WallapopScraper()
    items = s.parse_html(WALLAPOOPO_HTML, Category.RAM)
    assert len(items) == 1
    assert items[0].price == 105.0
    assert items[0].lat == 45.46
    assert items[0].shipping is True


async def test_demo_scraper_returns_listings():
    from bot.scraper.demo import DemoScraper
    p = SearchParams(sources=["demo"], category=Category.RAM)
    items = await DemoScraper().search(p)
    assert items and all(i.price > 0 for i in items)
