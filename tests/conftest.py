import sys

import pytest
from fastapi.testclient import TestClient
from app import main
from playwright.sync_api import sync_playwright


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'resume.sqlite3')
    # uvloop avoids socket-based thread wakeups blocked by restricted sandboxes.
    with TestClient(main.app, backend_options={'use_uvloop': sys.platform != 'win32'}) as client:
        yield client


@pytest.fixture
def browser_page(client):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': 1200, 'height': 900}, accept_downloads=True)

        def serve(route):
            request = route.request
            response = client.request(request.method, request.url, content=request.post_data,
                                      headers=request.headers)
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)

        page.route('http://testserver/**', serve)
        page.goto('http://testserver/')
        try:
            yield page
        finally:
            browser.close()
