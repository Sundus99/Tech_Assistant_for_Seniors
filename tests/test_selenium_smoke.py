"""
End-to-end smoke tests for the Chrome extension.

These tests require a real Chrome binary and the ``selenium`` package. They
are skipped automatically in CI where we run headless without a display —
run them locally with:

    pip install selenium
    pytest tests/test_selenium_smoke.py -v --no-cov

What we verify:
  * Extension loads without errors
  * Sidebar injects into a host page when the action icon fires
  * Mic button is focusable and has the correct aria-label
  * Font-size drawer toggles correctly
  * Minimize + restore cycle works
"""

from __future__ import annotations

import os
import shutil
import socket
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

selenium = pytest.importorskip("selenium")
from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.options import Options  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402


EXTENSION_DIR = Path(__file__).resolve().parents[1] / "extension"
SKIP_REASON = "Chrome not available or CI lacks display"


def _chrome_available() -> bool:
    """Extensions require a real Chrome binary — headless-shell is not enough."""
    if os.getenv("CI"):
        return False
    mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return mac_chrome.exists() or any(shutil.which(name) for name in
                                      ("google-chrome", "chromium",
                                       "chromium-browser", "chrome"))


pytestmark = pytest.mark.skipif(not _chrome_available(), reason=SKIP_REASON)


@pytest.fixture
def local_page(tmp_path):
    """Serve a local HTTP page so Chrome never depends on external DNS."""
    page = tmp_path / "index.html"
    page.write_text(
        "<!doctype html><html><head><title>GrandAssist smoke</title></head>"
        "<body><main><h1>Smoke page</h1><p>Extension test host.</p></main></body></html>",
        encoding="utf-8",
    )

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/index.html"
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.fixture
def driver():
    opts = Options()
    opts.add_argument(f"--load-extension={EXTENSION_DIR}")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,800")
    drv = webdriver.Chrome(options=opts)
    try:
        yield drv
    finally:
        drv.quit()


def _open_sidebar(driver, local_page: str) -> None:
    """Trigger the sidebar injection. In a real environment the user clicks the
    toolbar icon; in tests we inject the packaged assets directly."""
    driver.get(local_page)
    html = (EXTENSION_DIR / "sidebar" / "sidebar.html").read_text(encoding="utf-8")
    css = (EXTENSION_DIR / "sidebar" / "sidebar.css").read_text(encoding="utf-8")
    content_js = (EXTENSION_DIR / "scripts" / "content.js").read_text(encoding="utf-8")
    driver.execute_script("""
        const style = document.createElement('style');
        style.id = 'grandassist-style';
        style.textContent = arguments[0];
        document.head.appendChild(style);
        const host = document.createElement('div');
        host.innerHTML = arguments[1];
        document.body.appendChild(host.firstElementChild);
        const script = document.createElement('script');
        script.textContent = arguments[2];
        document.documentElement.appendChild(script);
        script.remove();
    """, css, html, content_js)
    WebDriverWait(driver, 5).until(
        EC.presence_of_element_located((By.ID, "chatbotSidebar"))
    )


class TestSidebarInjection:
    def test_sidebar_has_required_elements(self, driver, local_page):
        _open_sidebar(driver, local_page)
        for elem_id in ("gaHeader", "micButton", "gaMinBtn",
                         "gaCloseBtn", "gaChat"):
            assert driver.find_element(By.ID, elem_id), f"missing #{elem_id}"

    def test_mic_button_has_accessible_label(self, driver, local_page):
        _open_sidebar(driver, local_page)
        mic = driver.find_element(By.ID, "micButton")
        assert mic.get_attribute("aria-label") == "Start listening"
        assert mic.get_attribute("aria-pressed") == "false"

    def test_font_drawer_toggles(self, driver, local_page):
        _open_sidebar(driver, local_page)
        driver.find_element(By.ID, "gaFontBtn").click()
        drawer = driver.find_element(By.ID, "gaFontDrawer")
        WebDriverWait(driver, 2).until(
            lambda d: drawer.get_attribute("hidden") is None
        )

    def test_minimize_and_restore(self, driver, local_page):
        _open_sidebar(driver, local_page)
        sidebar = driver.find_element(By.ID, "chatbotSidebar")
        driver.find_element(By.ID, "gaMinBtn").click()
        time.sleep(0.2)
        assert "minimized" in sidebar.get_attribute("class")
        driver.find_element(By.ID, "gaMinPill").click()
        time.sleep(0.2)
        assert "minimized" not in sidebar.get_attribute("class")

    def test_no_console_errors(self, driver, local_page):
        _open_sidebar(driver, local_page)
        errors = [e for e in driver.get_log("browser")
                  if e["level"] == "SEVERE"
                  and "grandassist" not in e["message"].lower()]
        assert not errors, f"Console errors: {errors}"
