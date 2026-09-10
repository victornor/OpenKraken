## Why

OpenKraken's LCD modes are a split: sensor screens are live data on a plain ground, and animated GIFs are motion with no readout. Captain wants both at once — the sensor overlay on a moving background — plus a GIPHY browser so a background can be picked the way Discord or Facebook pick GIFs, without dropping local files.

## What Changes

- Add a new LCD display mode, `sensors_gif`, that composites the existing sensor-screen styles over an animated GIF background and is selectable alongside liquid / sensors / static / gif / off.
- Play that animation in firmware (pre-composite the current readings into the GIF, upload via the existing `set_lcd_gif` path, re-upload when displayed values change). Do **not** host-stream composited frames at GIF frame rate — that would be ~8 MB/s USB at 10 fps and would hammer HID bucket-switches.
- Persist the chosen background across restart (`gif_path`, same config conventions as today).
- Let the background come from a local GIF **or** from GIPHY. GIPHY is an addition, not a replacement; the same picker is offered for plain `gif` mode because both modes already share `gif_path`.
- Add a GIPHY browser: search, trending/categories, animated preview grid, selection downloads a local copy. Network only from that UI — never at startup, never while merely rendering.
- First-class unhappy paths in the browser: missing API key, no network, rate limited, empty results.
- Keep existing modes, the six-bucket sensor ring, software failsafe, and offline tests unchanged. No PyQt6 in base deps; no hardcoded GIPHY key; no usage telemetry.

**Not breaking:** unknown `lcd.mode` values already round-trip as strings; older configs without the new mode keep working.

## Capabilities

### New Capabilities

- `lcd-display`: LCD display modes, including the new sensor-over-GIF mode, background persistence, compositing/refresh contract (frame rate, data interval, USB, bucket behaviour), and overlay legibility.
- `giphy-browser`: In-app GIPHY search and category/trending browse, animated previews, local-file fallback, attribution, key/network/rate-limit/empty-result handling, and the "no network except from the browser" rule.

### Modified Capabilities

- (none — `openspec/specs/` is empty; this change introduces the LCD/GIPHY capabilities rather than delta-ing archived ones)

## Impact

- `openkraken/config.py` — new `lcd.mode` value; optional GIPHY id on the chosen background.
- `openkraken/backend/lcd_render.py` — render sensor styles over a background frame with a scrim.
- `openkraken/backend/engine.py` — `sensors_gif` tick: bake overlay, `set_lcd_gif`, value-change gating.
- `openkraken/backend/device.py` — reuse `set_lcd_gif` / `_set_screen` recovery; do not route this mode through `set_lcd_sensor_frame`.
- `openkraken/gui/pages/lcd.py` — new mode radio, GIPHY + local picker, preview of overlay on the GIF.
- Settings: a GIPHY API key field persisted in `~/.config/openkraken/config.json` (primary). Env `GIPHY_API_KEY` overrides for development. Never commit, log, or ship a default key.
- New modules: GIPHY client (stdlib `urllib`), background-frame cache under `~/.config/openkraken/media/`.
- Tests (no device): compositing, config round-trip, GIPHY client error mapping, engine upload on a faked driver. Existing `tests/test_lcd_bucket_ring.py` must still pass.
- README FAQ: document the stated animation fps, data refresh, and USB numbers.
- No new runtime dependencies. GIPHY key is an env var, never committed or logged.
