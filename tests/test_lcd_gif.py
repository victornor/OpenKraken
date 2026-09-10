"""Offline tests for GIF prepare, overlay bake, and displayed-int gating."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from openkraken.backend import lcd_gif, lcd_render
from openkraken.config import AppConfig, LcdConfig


def _write_gif(path: Path, count: int = 30, size: tuple[int, int] = (200, 80)) -> None:
    frames = [Image.new("RGB", size, (i * 7 % 256, 40, 80)) for i in range(count)]
    frames[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
    )


class LcdGifTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_prepare_caps_and_resizes_then_reuses(self) -> None:
        src = self.root / "src.gif"
        _write_gif(src, count=30)
        first = lcd_gif.prepare(str(src), media_dir=self.root)
        frames, delays, meta = lcd_gif.load_cache(first)
        self.assertLessEqual(len(frames), lcd_gif.MAX_FRAMES)
        self.assertEqual(frames[0].size, (640, 640))
        self.assertEqual(meta["count"], len(frames))
        self.assertEqual(len(delays), len(frames))
        second = lcd_gif.prepare(str(src), media_dir=self.root)
        self.assertEqual(first, second)

    def test_displayed_key_ignores_rpm(self) -> None:
        a = lcd_render.LcdData(35.2, 50.4, 10.2, 40.1, 20.6, 1200, 800)
        b = lcd_render.LcdData(35.4, 50.4, 10.2, 40.1, 20.6, 1800, 400)
        c = lcd_render.LcdData(36.0, 50.4, 10.2, 40.1, 20.6, 1200, 800)
        self.assertEqual(lcd_gif.displayed_key(a), lcd_gif.displayed_key(b))
        self.assertNotEqual(lcd_gif.displayed_key(a), lcd_gif.displayed_key(c))

    def test_bake_overlays_and_stays_under_hard_cap(self) -> None:
        src = self.root / "src.gif"
        _write_gif(src, count=8)
        cache = lcd_gif.prepare(str(src), media_dir=self.root)
        data = lcd_render.LcdData(36.0, 55.0, 20.0, 50.0, 10.0, 1000, 800)
        dest = str(self.root / "baked.gif")
        out = lcd_gif.bake(cache, "liquid_ring", data, dest_path=dest)
        self.assertTrue(Path(out).is_file())
        self.assertLessEqual(Path(out).stat().st_size, lcd_gif.HARD_MAX_BYTES)
        with Image.open(out) as gif:
            self.assertEqual(gif.size, (640, 640))

    def test_config_sensors_gif_round_trip_missing_path(self) -> None:
        cfg = AppConfig()
        cfg.lcd = LcdConfig(mode="sensors_gif", gif_path="/no/such/file.gif")
        cfg.giphy_api_key = "stored-key"
        restored = AppConfig.from_dict(cfg.to_dict())
        self.assertEqual(restored.lcd.mode, "sensors_gif")
        self.assertEqual(restored.lcd.gif_path, "/no/such/file.gif")
        self.assertEqual(restored.giphy_api_key, "stored-key")

    def test_render_without_background_stays_640(self) -> None:
        data = lcd_render.LcdData(30.0, None, None, None, None, None, None)
        for style in lcd_render.STYLES:
            img = lcd_render.render(style, data)
            self.assertEqual(img.size, (640, 640))
            self.assertEqual(img.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
