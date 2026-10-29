"""The simple demo page (demo/static/simple.*) only uses what the demo server serves."""

import re
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo"


def test_the_simple_page_calls_only_routes_the_server_has():
    js = (DEMO / "static" / "simple.js").read_text(encoding="utf-8")
    server = (DEMO / "app.py").read_text(encoding="utf-8")
    routes = set(re.findall(r'"(/api/[a-z/-]+)"', js))
    assert routes >= {"/api/status", "/api/reports", "/api/ask/ai", "/api/ask/draft", "/api/ask", "/api/plant", "/api/run"}
    for route in routes:
        assert f'"{route}"' in server, route


def test_the_simple_page_loads_its_own_files():
    html = (DEMO / "static" / "simple.html").read_text(encoding="utf-8")
    assert 'src="simple.js"' in html and 'href="simple.css"' in html
    assert (DEMO / "static" / "simple.js").exists() and (DEMO / "static" / "simple.css").exists()
