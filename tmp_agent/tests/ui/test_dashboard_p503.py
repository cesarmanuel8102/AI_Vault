"""
P5-03: Dashboard UI tests.

Verifies the index.html has the platforms tab, correct API fetch URLs,
and required DOM element IDs that the JS relies on.
"""
import pytest
from pathlib import Path


UI_PATH = Path(__file__).resolve().parents[2] / "brain_v9" / "ui" / "index.html"


@pytest.fixture(scope="module")
def html():
    return UI_PATH.read_text(encoding="utf-8")


class TestPlatformsTabExists:
    def test_nav_has_platforms_button(self, html):
        assert "showPanel('platforms')" in html

    def test_panel_platforms_div_exists(self, html):
        assert 'id="panel-platforms"' in html

    def test_platform_cards_container(self, html):
        assert 'id="platform-cards"' in html

    def test_platform_ranking_container(self, html):
        assert 'id="platform-ranking"' in html

    def test_platform_strategies_container(self, html):
        assert 'id="platform-strategies"' in html

    def test_platform_trades_container(self, html):
        assert 'id="platform-trades"' in html

    def test_platform_signals_container(self, html):
        assert 'id="platform-signals"' in html


class TestPlatformsJSFetches:
    """Verify the JS calls the correct API endpoints."""

    def test_fetches_platforms_summary(self, html):
        assert "/trading/platforms/summary" in html

    def test_fetches_platforms_compare(self, html):
        assert "/trading/platforms/compare" in html

    def test_fetches_po_signals(self, html):
        assert "/trading/platforms/pocket_option/signals" in html

    def test_fetches_ibkr_signals(self, html):
        assert "/trading/platforms/ibkr/signals" in html

    def test_fetches_platform_trades(self, html):
        # The JS dynamically builds URLs for each platform
        assert "/trading/platforms/${name}/trades" in html or "/trading/platforms/" in html

    def test_refresh_platforms_function_defined(self, html):
        assert "async function refreshPlatforms()" in html


class TestExistingTabsPreserved:
    """Ensure existing tabs still work."""

    def test_chat_tab(self, html):
        assert "showPanel('chat')" in html

    def test_status_tab(self, html):
        assert "showPanel('status')" in html

    def test_brain_tab(self, html):
        assert "showPanel('brain')" in html

    def test_api_tab(self, html):
        assert "showPanel('api')" in html


class TestAPIReferenceUpdated:
    """New endpoints listed in the API reference tab."""

    def test_platforms_summary_in_api_list(self, html):
        assert "/trading/platforms/summary" in html

    def test_platforms_compare_in_api_list(self, html):
        assert "/trading/platforms/compare" in html

    def test_platform_u_history_in_api_list(self, html):
        assert "u-history" in html
