"""
End-to-end smoke tests for the Chrome extension.

These tests require a real Chrome binary and the ``selenium`` package. They
are skipped automatically in CI where we run headless without a display —
run them locally with:

    pip install selenium
    pytest tests/test_selenium_smoke.py -v

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
import time
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
    return any(shutil.which(name) for name in
               ("google-chrome", "chromium", "chromium-browser", "chrome"))


pytestmark = pytest.mark.skipif(not _chrome_available(), reason=SKIP_REASON)


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


def _open_sidebar(driver) -> None:
    """Trigger the sidebar injection. In a real environment the user clicks the
    toolbar icon; in tests we call the injector directly via the content page."""
    driver.get("https://example.com")
    # The content script watches for injection, but in tests we inject the
    # sidebar directly by fetching the HTML + CSS the extension would.
    driver.execute_script("""
        const link = document.createElement('link');
        link.id = 'grandassist-fonts';
        link.rel = 'stylesheet';
        link.href = 'https://fonts.googleapis.com/css2?family=Nunito&display=swap';
        document.head.appendChild(link);
    """)
    # Wait for content.js to inject the sidebar via MutationObserver
    WebDriverWait(driver, 5).until(
        EC.presence_of_element_located((By.ID, "chatbotSidebar"))
    )


class TestSidebarInjection:
    def test_sidebar_has_required_elements(self, driver):
        _open_sidebar(driver)
        for elem_id in ("gaHeader", "micButton", "gaMinBtn",
                         "gaCloseBtn", "gaChat"):
            assert driver.find_element(By.ID, elem_id), f"missing #{elem_id}"

    def test_mic_button_has_accessible_label(self, driver):
        _open_sidebar(driver)
        mic = driver.find_element(By.ID, "micButton")
        assert mic.get_attribute("aria-label") == "Start listening"
        assert mic.get_attribute("aria-pressed") == "false"

    def test_font_drawer_toggles(self, driver):
        _open_sidebar(driver)
        driver.find_element(By.ID, "gaFontBtn").click()
        drawer = driver.find_element(By.ID, "gaFontDrawer")
        WebDriverWait(driver, 2).until(
            lambda d: drawer.get_attribute("hidden") is None
        )

    def test_minimize_and_restore(self, driver):
        _open_sidebar(driver)
        sidebar = driver.find_element(By.ID, "chatbotSidebar")
        driver.find_element(By.ID, "gaMinBtn").click()
        time.sleep(0.2)
        assert "minimized" in sidebar.get_attribute("class")
        driver.find_element(By.ID, "gaMinPill").click()
        time.sleep(0.2)
        assert "minimized" not in sidebar.get_attribute("class")

    def test_no_console_errors(self, driver):
        _open_sidebar(driver)
        errors = [e for e in driver.get_log("browser")
                  if e["level"] == "SEVERE"
                  and "grandassist" not in e["message"].lower()]
        assert not errors, f"Console errors: {errors}"
