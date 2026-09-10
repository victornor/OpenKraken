"""Engine sensors_gif path against a faked device. Needs offscreen Qt."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except Exception as exc:  # pragma: no cover
    raise unittest.SkipTest(f"PyQt6 unavailable: {exc}") from exc

from PIL import Image

from openkraken.backend.device import DeviceStatus, KrakenDevice
from openkraken.backend.engine import ControlEngine
from openkraken.backend.sensors import SystemSensors, SystemSnapshot
from openkraken.config import AppConfig, LcdConfig


def _gif(path: Path) -> None:
    frames = [Image.new("RGB", (64, 64), (i * 20, 0, 80)) for i in range(4)]
    frames[0].save(path, format="GIF", save_all=True, append_images=frames[1:], duration=80, loop=0)


class _FakeDev:
    is_connected = True
    lcd_bulk_unavailable = False

    def __init__(self) -> None:
        self.gifs: list[str] = []
        self.sensor_frames: list[str] = []

    def set_lcd_gif(self, path: str) -> bool:
        self.gifs.append(path)
        return True

    def set_lcd_sensor_frame(self, path: str) -> bool:
        self.sensor_frames.append(path)
        return True


class SensorsGifEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.gif_path = self.root / "bg.gif"
        _gif(self.gif_path)
        self._media = patch("openkraken.backend.lcd_gif.MEDIA_DIR", self.root)
        self._media.start()

    def tearDown(self) -> None:
        self._media.stop()
        self._tmp.cleanup()

    def _engine(self) -> tuple[ControlEngine, _FakeDev]:
        cfg = AppConfig()
        cfg.lcd = LcdConfig(mode="sensors_gif", gif_path=str(self.gif_path), sensor_interval=0.01)
        engine = ControlEngine(KrakenDevice(), SystemSensors(), cfg)
        fake = _FakeDev()
        engine._device = fake  # type: ignore[assignment]
        engine._lcd_cfg = cfg.lcd
        engine._gif_last_key = None
        engine._gif_missing_notified = False
        engine._last_lcd_push = 0.0
        return engine, fake

    def _sample(self, liquid: float = 35.0) -> tuple[DeviceStatus, SystemSnapshot]:
        status = DeviceStatus(
            liquid_temp=liquid,
            pump_rpm=1000,
            pump_duty=50,
            fan_rpm=800,
            fan_duty=40,
            connected=True,
            timestamp=time.monotonic(),
        )
        snap = SystemSnapshot(
            cpu_temp=50.0,
            cpu_load=10.0,
            cpu_freq_mhz=None,
            gpu_temp=40.0,
            gpu_load=5.0,
            gpu_vram_used_mb=None,
            gpu_vram_total_mb=None,
            gpu_power_w=None,
            ram_used_gb=None,
            ram_total_gb=None,
            timestamp=time.monotonic(),
        )
        return status, snap

    def _wait_bake(self, engine: ControlEngine) -> None:
        deadline = time.monotonic() + 8.0
        while engine._gif_bake_busy and time.monotonic() < deadline:
            time.sleep(0.05)
        engine._drain_requests()

    def test_uploads_gif_not_sensor_frame_only_on_value_change(self) -> None:
        engine, fake = self._engine()
        status, snap = self._sample(35.0)
        engine._last_lcd_push = 0.0
        engine._tick_lcd_sensors_gif(status, snap)
        self._wait_bake(engine)
        self.assertTrue(fake.gifs, "expected a GIF upload")
        self.assertEqual(fake.sensor_frames, [])
        n = len(fake.gifs)
        engine._last_lcd_push = 0.0
        engine._tick_lcd_sensors_gif(status, snap)
        self._wait_bake(engine)
        self.assertEqual(len(fake.gifs), n, "unchanged ints must not re-upload")
        engine._last_lcd_push = 0.0
        status2, snap2 = self._sample(38.0)
        engine._tick_lcd_sensors_gif(status2, snap2)
        self._wait_bake(engine)
        self.assertGreater(len(fake.gifs), n)

    def test_missing_file_skips_device(self) -> None:
        engine, fake = self._engine()
        engine._lcd_cfg.gif_path = str(self.root / "gone.gif")
        engine._last_lcd_push = 0.0
        engine._tick_lcd_sensors_gif(*self._sample())
        self._wait_bake(engine)
        self.assertEqual(fake.gifs, [])
        self.assertEqual(fake.sensor_frames, [])


if __name__ == "__main__":
    unittest.main()
