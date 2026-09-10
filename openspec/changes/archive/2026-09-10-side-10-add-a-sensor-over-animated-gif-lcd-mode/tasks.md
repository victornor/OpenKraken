## 1. Config and mode plumbing

- [x] 1.1 Add `sensors_gif` as an `LcdConfig.mode` value (tolerant load/save, shared `gif_path`) and verify a round-trip of `mode=sensors_gif` plus a missing-file `gif_path` does not raise
- [x] 1.2 Show the new mode on the LCD page (radio after Sensor screen; sensor style/interval/ring-color + media picker visible) and verify the page constructs an `LcdConfig` with `mode=sensors_gif` without applying to a device

## 2. Background cache and overlay render

- [x] 2.1 Implement selection-time GIF prepare (square crop, 640×640, ≤24 frames, `media/gif-bg/<sha12>/` PNG frames + `meta.json`) and verify a multi-frame fixture is capped, sized, and reused on a second prepare of the same file
- [x] 2.2 Extend `lcd_render` to composite a sensor style over a background frame with a ~50% circular scrim and number drop shadow, and verify `render` still produces 640×640 RGB for the three existing styles with no background
- [x] 2.3 Add a bake helper that overlays current `LcdData` onto cached frames, writes a GIF (target ≤4 MB, never >24 MB), and verify integer-unchanged `LcdData` can be detected as a no-op for re-upload gating

## 3. Engine firmware-playback path

- [x] 3.1 On `apply_lcd(sensors_gif)`, skip `set_lcd_sensor_frame`; on the engine tick, bake off-thread when displayed ints change and ≥ `sensor_interval`, then `set_lcd_gif` on the engine thread, and verify a faked device receives GIF uploads (not sensor frames) only on value change
- [x] 3.2 If `gif_path` or the frame cache is missing, skip the upload, emit a clear error, stay in mode, and verify a faked device is not called
- [x] 3.3 On swallowed GIF bucket failure after existing `_set_screen` recovery, leave the previous animation and do not mark the device disconnected; verify with the existing fake-driver pattern

## 4. GIPHY client

- [x] 4.1 Add a stdlib GIPHY client using Settings `giphy_api_key` with env `GIPHY_API_KEY` override (search, trending, categories, download to `media/giphy/<id>.gif`) and verify mocked HTTP covers success, empty list, 429, network error, and missing key with no request sent
- [x] 4.2 Ensure the client never logs the key and is not imported from app startup or the engine render path; verify grep/tests that engine bake uses only local paths
- [x] 4.3 Add a Settings field for the GIPHY API key persisted in config.json, and verify round-trip plus missing-key copy that names Settings and developers.giphy.com

## 5. GIPHY browser UI

- [x] 5.1 Add a GIPHY dialog (search, trending/categories, animated preview grid, Powered by GIPHY, local Choose file) opened from the LCD media picker for `gif` and `sensors_gif`, with network/decode off the UI thread and preview cache, and verify missing key / no network / 429 / empty each show a distinct message in the widget (no live GIPHY)
- [x] 5.2 On GIPHY select, save the local copy, run the prepare pipeline, set `gif_path`, and verify a second search of the same id hits the preview cache
- [x] 5.3 Preview sensor-over-GIF on the LCD page as overlay-on-first-cached-frame (2 s timer, no GIF fps in-process) and verify a missing `gif_path` shows a missing-file placeholder

## 6. Docs and offline suite

- [x] 6.1 Document the animation fps, data-refresh rule, USB burst, Settings GIPHY key, and `GIPHY_API_KEY` override in the README FAQ and verify the numbers match design.md
- [x] 6.2 Run `python3 -m unittest discover -s tests` and `QT_QPA_PLATFORM=offscreen python3 scripts/smoke_test.py` and verify both pass with no cooler attached, including existing `test_lcd_bucket_ring.py`
