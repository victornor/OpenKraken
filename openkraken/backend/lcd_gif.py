"""Prepare and bake 640×640 GIF backgrounds for the sensor-over-GIF LCD mode.

Selection-time :func:`prepare` crops, resizes and frame-caps a source GIF into
PNG frames under the media cache. Later :func:`bake` overlays the current
sensor screen onto those cached frames and writes a firmware-playable GIF.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from PIL import Image

from openkraken.backend import lcd_render
from openkraken.config import MEDIA_DIR

_LOGGER = logging.getLogger(__name__)

CANVAS = lcd_render.CANVAS
MAX_FRAMES = 24
MAX_DURATION_MS = 6000
TARGET_BYTES = 4 * 1024 * 1024
HARD_MAX_BYTES = 24 * 1024 * 1024
_CACHE_ROOT = "gif-bg"
_META_NAME = "meta.json"


class GifPrepareError(Exception):
    """Source GIF could not be prepared."""


def cache_dir_for(source_path: str, media_dir: Path | None = None) -> Path:
    """Return the cache directory for *source_path* (may not exist yet)."""
    root = Path(media_dir) if media_dir is not None else MEDIA_DIR
    digest = _file_sha12(source_path)
    return root / _CACHE_ROOT / digest


def prepare(source_path: str, media_dir: Path | None = None) -> Path:
    """Decode *source_path* into a 640×640 frame cache; return the cache dir.

    Reuses an existing complete cache for the same file bytes.
    """
    src = Path(source_path)
    if not src.is_file():
        raise GifPrepareError(f"GIF not found: {source_path}")
    dest = cache_dir_for(source_path, media_dir)
    if _cache_complete(dest):
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    frames, delays = _extract_frames(src)
    frames, delays = _cap_frames(frames, delays)
    for i, frame in enumerate(frames):
        frame.save(dest / f"frame_{i:04d}.png", format="PNG")
    meta = {
        "source": str(src.resolve()),
        "sha12": dest.name,
        "count": len(frames),
        "delays_ms": delays,
    }
    (dest / _META_NAME).write_text(json.dumps(meta), encoding="utf-8")
    return dest


def load_cache(cache: Path) -> tuple[list[Image.Image], list[int], dict[str, Any]]:
    """Load cached RGB frames, delays (ms), and meta. Raises if incomplete."""
    if not _cache_complete(cache):
        raise GifPrepareError(f"incomplete GIF cache: {cache}")
    meta = json.loads((cache / _META_NAME).read_text(encoding="utf-8"))
    count = int(meta["count"])
    delays = [int(d) for d in meta["delays_ms"]]
    frames = [Image.open(cache / f"frame_{i:04d}.png").convert("RGB") for i in range(count)]
    return frames, delays, meta


def displayed_key(data: lcd_render.LcdData) -> tuple:
    """Integer readings that gate a firmware GIF re-upload (RPM excluded)."""
    return (
        _round_or_none(data.liquid_temp),
        _round_or_none(data.cpu_temp),
        _round_or_none(data.cpu_load),
        _round_or_none(data.gpu_temp),
        _round_or_none(data.gpu_load),
    )


def bake(
    cache: Path,
    style: str,
    data: lcd_render.LcdData,
    dest_path: str | None = None,
) -> str:
    """Composite *data* over cached frames and write a GIF; return *dest_path*."""
    frames, delays, _meta = load_cache(cache)
    composited: list[Image.Image] = []
    for frame in frames:
        composited.append(lcd_render.render(style, data, background=frame))
    path = dest_path or default_bake_path()
    _save_gif(composited, delays, path)
    return path


def default_bake_path() -> str:
    """Prefer tmpfs so repeated bakes do not wear an SSD."""
    if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK):
        return "/dev/shm/openkraken_sensors_gif.gif"
    return str(Path("/tmp") / "openkraken_sensors_gif.gif")


def first_cached_frame(cache: Path) -> Image.Image | None:
    """Return frame 0 of a complete cache, or None."""
    try:
        frames, _delays, _meta = load_cache(cache)
    except (GifPrepareError, OSError, ValueError, KeyError):
        return None
    return frames[0] if frames else None


def _round_or_none(value: float | None) -> int | None:
    if value is None:
        return None
    return int(round(value))


def _file_sha12(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _cache_complete(dest: Path) -> bool:
    meta_path = dest / _META_NAME
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        count = int(meta["count"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if count < 1:
        return False
    return all((dest / f"frame_{i:04d}.png").is_file() for i in range(count))


def _extract_frames(src: Path) -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    delays: list[int] = []
    try:
        with Image.open(src) as img:
            index = 0
            while True:
                img.seek(index)
                frames.append(_fit_frame(img))
                delays.append(_frame_delay_ms(img))
                index += 1
    except EOFError:
        pass
    except OSError as exc:
        raise GifPrepareError(f"cannot read GIF: {src}") from exc
    if not frames:
        raise GifPrepareError(f"no frames in GIF: {src}")
    return frames, delays


def _fit_frame(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    w, h = rgb.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = rgb.crop((left, top, left + side, top + side))
    if cropped.size != (CANVAS, CANVAS):
        cropped = cropped.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)
    return cropped


def _frame_delay_ms(img: Image.Image) -> int:
    info = getattr(img, "info", None) or {}
    delay = info.get("duration", 100)
    try:
        ms = int(delay)
    except (TypeError, ValueError):
        ms = 100
    return max(20, ms)


def _cap_frames(
    frames: list[Image.Image], delays: list[int]
) -> tuple[list[Image.Image], list[int]]:
    n = len(frames)
    if n > MAX_FRAMES:
        indices = [round(i * (n - 1) / (MAX_FRAMES - 1)) for i in range(MAX_FRAMES)]
        picked = [frames[i] for i in indices]
        # Preserve loop duration by grouping source delays between picks.
        new_delays: list[int] = []
        for k, src_i in enumerate(indices):
            nxt = indices[k + 1] if k + 1 < len(indices) else n
            new_delays.append(sum(delays[src_i:nxt]) or 100)
        frames, delays = picked, new_delays
    total = sum(delays)
    if total > MAX_DURATION_MS and total > 0:
        scale = MAX_DURATION_MS / total
        delays = [max(20, int(d * scale)) for d in delays]
    return frames, delays


def _save_gif(frames: list[Image.Image], delays: list[int], path: str) -> None:
    if not frames:
        raise GifPrepareError("no frames to bake")
    first, rest = frames[0], frames[1:]
    first.save(
        path,
        format="GIF",
        save_all=bool(rest),
        append_images=rest,
        duration=delays,
        loop=0,
        optimize=True,
    )
    size = os.path.getsize(path)
    if size > TARGET_BYTES and len(frames) > 8:
        step = max(2, len(frames) // 12)
        reduced = frames[::step]
        reduced_delays = delays[::step]
        _LOGGER.info("baked GIF %d bytes; reducing to %d frames", size, len(reduced))
        _save_gif(reduced, reduced_delays, path)
        return
    if size > HARD_MAX_BYTES:
        os.unlink(path)
        raise GifPrepareError(f"baked GIF exceeds 24 MB ({size} bytes)")
