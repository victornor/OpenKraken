## Context

See proposal.md for motivation. Today's LCD split is host-rendered sensor PNGs at 2 s (`lcd_render` → `set_lcd_sensor_frame`, six-bucket ring) versus one-shot firmware GIF playback (`set_lcd_gif`, 24 MB cap). Each 640×640 frame is ~0.8 MB over the USB bulk interface; bucket setup/switch is HID, shared with cooling and lighting. Firmware has no overlay API. Live cooler must not be used as a casual check; offline tests fake the driver (`tests/test_lcd_bucket_ring.py`).

## Goals / Non-Goals

**Goals:**
- One compositing path whose USB, fps, and bucket behaviour are stated and testable without hardware.
- Prepare GIF frames once at selection; overlay every data refresh from that cache.
- GIPHY confined to a Qt dialog; stdlib HTTP; key from env.

**Non-Goals:**
- Firmware or liquidctl patches; MP4/WebP backgrounds; auto-contrast per frame; storing the API key in config; running hardware watch scripts during apply.

## Decisions

### 1. Pre-composite + firmware playback, not host-streamed frames

**Choice.** Bake current readings into every cached GIF frame, write a GIF under `/dev/shm`, upload with `set_lcd_gif`. Firmware loops the motion. Re-bake when displayed integer values change, not faster than `sensor_interval` (default 2 s). RPM is excluded from the change key (it chatters; footer may lag one interval).

**Stated contract**

| Quantity | Value |
|---|---|
| Animation fps | GIF frame delays after processing (typically 10–15 fps) |
| Frame cap | 24 frames; even subsample if the source is longer; loop duration capped at ~6 s |
| Data refresh | Displayed int °C / load % change, ≥ `sensor_interval` (default 2 s) |
| USB between refreshes | 0 LCD bytes (firmware plays) |
| USB per refresh | One GIF, target ≤ 4 MB, hard cap 24 MB (driver assertion) |
| Bucket ring | Idle. This mode does not call `set_lcd_sensor_frame` |
| Failed upload | Previous firmware animation stays up (`_set_screen` recovery already holds last good content) |

**Rejected: host-composite every animation frame.** At 10 fps that is ~8 MB/s bulk plus ~10 HID bucket-switch sequences/s on the same HID as cooling/lighting. The six-bucket ring would avoid the old 30-frame exhaustion, but HID desync (`missing messages`) is already a field failure at far lower rates. At 2 fps the background becomes a slideshow, which fails the “moving” requirement.

**Rejected: host-composite at 3–5 fps as a compromise.** Still continuous HID switches (6–10× current sensor mode) plus always-on USB, and motion still looks cheap next to firmware GIF playback.

Bake (composite + encode) runs on a worker thread so a multi-hundred-ms Pillow encode cannot stall cooling ticks. Only `set_lcd_gif` runs on the engine thread under the device lock. In-flight bakes coalesce.

### 2. Scrim + drop shadow, not per-frame contrast

**Choice.** Fill the inscribed circle with ~50% opaque black, then draw the existing sensor styles with a drop shadow on the primary numbers. Same three styles as today.

**Rejected:** auto luminance / outline per GIF (expensive, flicker on busy clips). **Rejected:** tiny caption without a scrim (unreadable on bright GIFs).

### 3. Resize and cap once at selection

**Choice.** On pick (local or GIPHY): decode, square centre-crop, 640×640, cap to 24 frames, write `~/.config/openkraken/media/gif-bg/<sha12>/` (`frame_XXXX.png` + `meta.json` with delays, source path, optional giphy id). Every later composite reads that cache.

**Rejected:** re-decode the source GIF every refresh (CPU and SSD). **Rejected:** keep a processed GIF without PNG frames (re-decoding GIF on each bake is slower than PNG).

### 4. GIPHY downloads become ordinary local files

**Choice.** Selected GIF is saved at `~/.config/openkraken/media/giphy/<id>.gif`, then runs the same selection pipeline. `LcdConfig.gif_path` points at that file (plain `gif` mode shares it). If the file is deleted: stay in mode, skip upload, UI shows missing-file; no silent re-fetch (that would be a network call outside the browser).

API: stdlib `urllib` like `updater.py`. Key: `GIPHY_API_KEY` (absent-by-default; missing key is a designed UI state, not a crash). Endpoints: `/v1/gifs/search`, `/trending`, `/categories`. Rating `pg-13`. Grid uses GIPHY preview/fixed-width URLs; selection prefers `downsized` then `original` GIF. Search debounced 300 ms. Preview cache: `media/giphy-preview/<id>.gif`. Qt work on a `QThread`; `QMovie` on the UI thread for grid playback. Dialog shows “Powered by GIPHY”. Never log the key.

GIPHY browser is offered for both `sensors_gif` and `gif` because they already share `gif_path`.

### 5. New mode value `sensors_gif`

Radio after “Sensor screen”. Config load stays tolerant; unknown keys ignored. `sensor_style`, `sensor_interval`, and `ring_color` apply to this mode as they do to `sensors`.

## Risks / Trade-offs

- **[Risk] Data steps rather than ticks** → Acceptable for °C; interval is the existing sensor control. Document in the README FAQ.
- **[Risk] Visible hitch when replacing the firmware GIF** → Cap 24 frames and target ≤ 4 MB so the burst is short; value-change gating avoids idle re-uploads. Hitch duration is not measured on live hardware in this change (charter: no casual LCD programming). If captain later wants a timed watch, that is a separate hardware run.
- **[Risk] Pillow GIF encode blocks cooling** → Encode off the engine thread; coalesce.
- **[Risk] Oversized source GIF** → Driver already treats >24 MB as recoverable (no disconnect). Selection pipeline must refuse or shrink before upload and surface the error.
- **[Risk] Busy GIF still fights the overlay** → Scrim is the mitigation; no adaptive contrast in this change.
- **[Risk] HID contention during GIF upload** → Same as today's plain GIF apply; lighting already re-asserts after LCD content changes.

## Migration Plan

No migration. New mode is opt-in. Existing configs keep `liquid` / `sensors` / `static` / `gif` / `off`. Rollback is revert; leftover files under `media/giphy/` and `media/gif-bg/` are cache and can be deleted by the user.

## Open Questions

None that block apply. The four ticket questions are decided above (firmware playback, scrim, cache-at-selection, local GIPHY copy with missing-file error).
