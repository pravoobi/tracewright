"""Browser-level regression test for the Generator's SSRF origin guard.

Found live: route.continue_() let Chromium follow a cross-origin 302 without
re-running the handler. Needs Playwright's Chromium (skipped if unavailable);
uses only local servers -- no DB, MinIO or LLM.
"""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.src.agents.generator.app_model import restrict_to_origin

pytest.importorskip("playwright")


def _serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def servers():
    hits: list[str] = []

    class Other(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"other")

        def log_message(self, *a):
            pass

    other = _serve(Other)
    other_url = f"http://127.0.0.1:{other.server_port}"

    class App(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/same":
                self.send_response(302)
                self.send_header("Location", "/ok")
                self.end_headers()
            elif self.path == "/ok":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
            else:  # /cross
                self.send_response(302)
                self.send_header("Location", other_url + "/secret")
                self.end_headers()

        def log_message(self, *a):
            pass

    app = _serve(App)
    yield f"http://127.0.0.1:{app.server_port}", other_url, hits
    app.shutdown()
    other.shutdown()


async def _goto(app_url, target):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as e:  # browser not installed
            pytest.skip(f"chromium unavailable: {e}")
        ctx = await browser.new_context()
        await restrict_to_origin(ctx, app_url)
        page = await ctx.new_page()
        try:
            await page.goto(target)
            body = await page.inner_text("body")
        except Exception:
            body = None
        await browser.close()
        return body


@pytest.mark.asyncio
async def test_cross_origin_redirect_not_followed(servers):
    app, _other, hits = servers
    assert await _goto(app, app + "/cross") is None
    assert hits == []


@pytest.mark.asyncio
async def test_direct_cross_origin_url_blocked(servers):
    app, other, hits = servers
    assert await _goto(app, other + "/direct") is None
    assert hits == []


@pytest.mark.asyncio
async def test_same_origin_redirect_still_followed(servers):
    app, _other, _hits = servers
    assert await _goto(app, app + "/same") == "ok"
