"""LCD page constructs sensors_gif config without touching a device."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QRadioButton
except Exception as exc:  # pragma: no cover
    raise unittest.SkipTest(f"PyQt6 unavailable: {exc}") from exc

from openkraken.backend.device import KrakenDevice
from openkraken.backend.engine import ControlEngine
from openkraken.backend.sensors import SystemSensors
from openkraken.config import AppConfig
from openkraken.gui.giphy_browser import GiphyBrowserDialog
from openkraken.gui.pages.lcd import LcdPage
from openkraken.gui.pages.settings import SettingsPage


class LcdPageSensorsGifTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _engine(self) -> tuple[ControlEngine, AppConfig]:
        cfg = AppConfig()
        cfg.check_updates_on_start = False
        engine = ControlEngine(KrakenDevice(), SystemSensors(), cfg)
        return engine, cfg

    def test_missing_gif_shows_placeholder(self) -> None:
        engine, cfg = self._engine()
        page = LcdPage(engine, cfg)
        page._mode_buttons["sensors_gif"].setChecked(True)
        page._lcd_cfg.gif_path = "/no/such/background.gif"
        page._render_sensors_gif_preview()
        self.assertIn("missing", page._preview._placeholder_text.lower())

    def test_page_builds_sensors_gif_config(self) -> None:
        engine, cfg = self._engine()
        page = LcdPage(engine, cfg)
        button = page._mode_buttons["sensors_gif"]
        self.assertIsInstance(button, QRadioButton)
        button.setChecked(True)
        built = page._build_config()
        self.assertEqual(built.mode, "sensors_gif")

    def test_giphy_dialog_missing_key_message(self) -> None:
        os.environ.pop("GIPHY_API_KEY", None)
        cfg = AppConfig()
        cfg.giphy_api_key = ""
        dialog = GiphyBrowserDialog(cfg)
        self.assertIn("Settings", dialog._status.text())
        self.assertIn("developers.giphy.com", dialog._status.text())
        dialog._on_failed("network", "Could not reach GIPHY. Check your network.")
        self.assertIn("network", dialog._status.text().lower())
        dialog._on_failed("rate_limited", "GIPHY rate limit reached. Try again later.")
        self.assertIn("rate", dialog._status.text().lower())
        dialog._on_listed([])
        self.assertIn("No GIFs", dialog._status.text())

    def test_settings_giphy_key_round_trip_widget(self) -> None:
        engine, cfg = self._engine()
        page = SettingsPage(engine, cfg)
        page._giphy_key.setText("user-supplied-key")
        with patch.object(cfg, "save"), patch.object(engine, "update_config"):
            page._save()
        self.assertEqual(cfg.giphy_api_key, "user-supplied-key")


if __name__ == "__main__":
    unittest.main()
