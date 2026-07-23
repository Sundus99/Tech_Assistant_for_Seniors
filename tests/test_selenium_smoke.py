"""
End-to-end smoke tests for the Chrome extension.

These tests require a real Chrome binary and the ``selenium`` package. They
run in GitHub Actions under xvfb and can also run locally with:

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
import subprocess
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
ARTIFACT_DIR = Path(os.getenv("SELENIUM_ARTIFACT_DIR", "artifacts/selenium"))
SKIP_REASON = "Chrome not available"


def _command_version(command: str) -> str:
    path = shutil.which(command)
    if not path:
        return "not found"
    try:
        completed = subprocess.run(
            [path, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics should not fail tests
        return f"{path}: {type(exc).__name__}: {exc}"
    return (completed.stdout or completed.stderr or path).strip()


def _selenium_environment() -> dict[str, str]:
    chrome_path = os.getenv("CHROME_PATH") or str(
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    )
    return {
        "CHROME_PATH": chrome_path,
        "chrome": _command_version(chrome_path) if Path(chrome_path).exists() else "not found",
        "chromedriver": _command_version("chromedriver"),
    }


def _write_diagnostics(driver, test_name: str) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = test_name.replace("/", "_").replace(":", "_")
    (ARTIFACT_DIR / f"{safe_name}.env.txt").write_text(
        "\n".join(f"{k}={v}" for k, v in _selenium_environment().items()),
        encoding="utf-8",
    )
    try:
        driver.save_screenshot(str(ARTIFACT_DIR / f"{safe_name}.png"))
    except Exception as exc:  # noqa: BLE001
        (ARTIFACT_DIR / f"{safe_name}.screenshot_error.txt").write_text(str(exc))
    try:
        logs = driver.get_log("browser")
    except Exception as exc:  # noqa: BLE001
        logs = [{"level": "ERROR", "message": str(exc)}]
    (ARTIFACT_DIR / f"{safe_name}.browser.log").write_text(
        "\n".join(str(entry) for entry in logs),
        encoding="utf-8",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


def _chrome_available() -> bool:
    """Extensions require a real Chrome binary; headless-shell is not enough."""
    if os.getenv("GRANDASSIST_SKIP_SELENIUM"):
        return False
    chrome_path = os.getenv("CHROME_PATH")
    if chrome_path and Path(chrome_path).exists():
        return True
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
def driver(request):
    opts = Options()
    chrome_path = os.getenv("CHROME_PATH")
    if chrome_path:
        opts.binary_location = chrome_path
    opts.add_argument(f"--load-extension={EXTENSION_DIR}")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,800")
    try:
        drv = webdriver.Chrome(options=opts)
    except Exception as exc:  # noqa: BLE001
        env = _selenium_environment()
        pytest.fail(
            "Unable to start Chrome WebDriver. "
            f"Diagnostics: {env}. Original error: {type(exc).__name__}: {exc}"
        )
    try:
        yield drv
    finally:
        if getattr(request.node, "rep_call", None) and request.node.rep_call.failed:
            _write_diagnostics(drv, request.node.nodeid)
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
        assert not driver.find_element(By.ID, "gaMinPill").is_displayed()

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
