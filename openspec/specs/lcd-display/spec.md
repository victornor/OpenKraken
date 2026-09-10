# lcd-display Specification

## Purpose
Defines how OpenKraken drives the Kraken's round LCD, including the sensor-over-animated-GIF mode, overlay legibility, background persistence, and the USB / firmware-playback contract that keeps the panel off a black screen.

## Requirements

### Requirement: Sensor-over-GIF display mode
The LCD mode list SHALL include a mode distinct from plain sensor screen and plain animated GIF that renders the selected sensor style over an animated GIF background. Existing modes (firmware liquid temperature, sensor screen, static image, animated GIF, screen off) MUST keep their current behaviour.

#### Scenario: New mode is selectable
- **WHEN** the user opens the LCD page
- **THEN** a sensor-over-GIF option is listed alongside the existing modes and can be applied

#### Scenario: Existing modes unchanged
- **WHEN** the user applies liquid, sensors, static, gif, or off
- **THEN** each mode behaves as it did before this change (firmware liquid, host-rendered sensor frames at `sensor_interval`, one-shot static/GIF upload, brightness 0 for off)

### Requirement: Firmware-played animation with stepping data
The sensor-over-GIF mode SHALL animate by uploading a pre-composited GIF for firmware playback, not by host-streaming every animation frame. Displayed sensor values MAY step when the composited GIF is replaced. The shipped contract MUST be:

- Animation frame rate: the processed GIF's own frame delays (native motion after the frame cap).
- Data refresh: when a displayed integer reading changes, and not more often than `sensor_interval` (default 2 s).
- USB: zero LCD payload between replacements; one GIF upload per replacement, encoded size at most 24 MB and targeted at or under 4 MB.
- Bucket ring: the six-bucket sensor-frame ring is not used for this mode. GIF upload uses the existing one-shot screen-set recovery. A failed replacement MUST leave the previous firmware animation showing (no black panel).

#### Scenario: Firmware plays the motion
- **WHEN** sensor-over-GIF is applied with a valid background
- **THEN** the cooler plays the composited animation from onboard memory at the GIF's frame delays without a host frame push per animation frame

#### Scenario: Data updates on a change, not every animation frame
- **WHEN** displayed integer temperatures or loads change and `sensor_interval` has elapsed
- **THEN** a new composited GIF is uploaded and subsequent animation loops show the new numbers

#### Scenario: Unchanged readings do not re-upload
- **WHEN** displayed integer readings are unchanged
- **THEN** the host does not re-upload the GIF and firmware keeps looping the last composited animation

### Requirement: Overlay stays legible over arbitrary GIFs
Sensor text and gauges SHALL remain readable over busy or bright GIF backgrounds. The overlay MUST include a dark circular scrim behind the content plus a drop shadow on the primary numbers. The existing sensor styles (liquid ring, CPU/GPU split, all sensors) MUST be available in this mode.

#### Scenario: Busy background still readable
- **WHEN** the background GIF is high-contrast or full of motion
- **THEN** the sensor numbers and labels remain readable because of the scrim and text shadow

### Requirement: Background is prepared once at selection
GIF frames SHALL be cropped, resized to 640×640, and frame-capped when the user selects a background, then reused on every later composite. Per-cycle work MUST NOT re-decode or re-resize the source GIF.

#### Scenario: Selection builds a 640×640 cache
- **WHEN** the user chooses a local or GIPHY GIF
- **THEN** processed 640×640 frames are stored under the app media directory and later composites read that cache

#### Scenario: Restart reuses the cache
- **WHEN** the application restarts with sensor-over-GIF still selected and the cache still present
- **THEN** the mode resumes without asking the user to pick the GIF again

### Requirement: Chosen background persists
The chosen GIF path MUST persist in config across an application restart using the existing tolerant JSON conventions. A GIPHY-sourced GIF MUST be stored as a local file under the media directory; `gif_path` MUST point at that file. If the file is later missing, the app MUST stay in the mode, skip the upload, and show a clear missing-file message rather than crashing or hanging.

#### Scenario: Restart restores the background
- **WHEN** the user applies sensor-over-GIF with a chosen GIF and restarts the app
- **THEN** the same background is selected and the mode can be re-applied

#### Scenario: Deleted background is a visible error
- **WHEN** the stored `gif_path` no longer exists
- **THEN** the UI reports that the background file is missing and the engine does not push a replacement GIF

### Requirement: Local file remains a way to supply a GIF
The user MUST be able to pick a GIF from the local filesystem as the background. GIPHY MUST NOT be required to use sensor-over-GIF.

#### Scenario: Local file only
- **WHEN** no GIPHY API key is configured and the user picks a local `.gif`
- **THEN** sensor-over-GIF uses that file as the background

### Requirement: Bucket self-heal still holds
The six-bucket sensor-frame ring and reconnect-after-consecutive-stream-failures behaviour MUST remain in force for plain sensor mode. Sensor-over-GIF MUST use the existing GIF upload recovery (retry / clear on swallowed bucket failure) and MUST NOT disable or weaken it. Offline tests MUST cover the new upload path with a faked driver and MUST NOT require a cooler.

#### Scenario: Plain sensor ring tests still pass
- **WHEN** the offline bucket-ring suite runs
- **THEN** it passes without a device attached

#### Scenario: Failed GIF replacement does not blank the panel
- **WHEN** a composited GIF upload hits a swallowed bucket failure that recovery cannot land
- **THEN** the previous firmware animation remains on screen and the device is not marked disconnected for that recoverable failure
