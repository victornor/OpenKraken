## Purpose

Defines the in-app GIPHY browser used to pick an LCD GIF background: search, category or trending browse, animated previews, local-file fallback, attribution, and first-class failure states, without network calls outside that UI.

## ADDED Requirements

### Requirement: Search and browse GIPHY
The LCD GIF picker SHALL offer a GIPHY browser with a text search field and category or trending browsing. Results MUST appear as a grid of animated previews. Choosing a result MUST download a local copy and set it as the GIF used by sensor-over-GIF (and by plain animated-GIF mode, which shares the same path).

#### Scenario: Text search
- **WHEN** the user types a query in the GIPHY browser and the request succeeds
- **THEN** a grid of matching animated previews is shown

#### Scenario: Trending or category browse
- **WHEN** the user opens the browser with an empty query, or picks a category
- **THEN** trending or that category's GIFs are shown in the same grid

#### Scenario: Selection becomes the background
- **WHEN** the user selects a preview
- **THEN** the GIF is stored locally under the app media directory and becomes the configured GIF path

### Requirement: Local files remain available
The picker MUST still allow choosing a GIF from the local filesystem. GIPHY is an addition, not a replacement.

#### Scenario: Choose from disk
- **WHEN** the user chooses a local `.gif` instead of a GIPHY result
- **THEN** that file is used as the GIF path and no GIPHY download occurs

### Requirement: UI thread stays responsive
Searching, scrolling the preview grid, and decoding preview images MUST NOT freeze the Qt UI thread. Preview fetches MUST be cached so repeating the same query or scrolling back does not re-download every keystroke.

#### Scenario: Typing does not freeze the window
- **WHEN** the user types in the search field
- **THEN** the window keeps painting and accepting input while the search runs off the UI thread

#### Scenario: Cached previews are reused
- **WHEN** the user re-runs a query or scrolls back to an already-fetched preview
- **THEN** the preview is served from the local cache rather than downloaded again

### Requirement: Unhappy paths are visible
Missing API key, no network, HTTP 429 rate limiting, and a successful search with zero results MUST each show a distinct, human-readable message in the browser. None of those cases MAY fail silently or hang.

#### Scenario: No API key
- **WHEN** no GIPHY API key is configured in Settings and the environment variable is unset or empty
- **THEN** the browser explains that a key is required and does not send a request

#### Scenario: No network
- **WHEN** a GIPHY request cannot be completed because of a network error
- **THEN** the browser shows a network-error message and leaves prior results or an empty grid, without hanging

#### Scenario: Rate limited
- **WHEN** GIPHY responds with HTTP 429
- **THEN** the browser shows a rate-limit message

#### Scenario: Empty results
- **WHEN** a search returns no GIFs
- **THEN** the browser shows that nothing matched

### Requirement: Network only from the browsing UI
The application MUST NOT call GIPHY at startup, while merely rendering the LCD, or on a timer in the engine. Queries MAY include the user's search text. The application MUST NOT send usage telemetry or any other outbound report.

#### Scenario: Startup makes no GIPHY call
- **WHEN** the application starts with sensor-over-GIF already configured
- **THEN** no GIPHY request is issued; the local file is used

#### Scenario: Rendering makes no GIPHY call
- **WHEN** the engine composites and uploads frames
- **THEN** it reads only local files and does not contact GIPHY

### Requirement: API key is not embedded or logged
The GIPHY API key MUST be user-configurable in Settings and persisted under `~/.config/openkraken` using the existing config conventions. The environment variable `GIPHY_API_KEY` MUST override the stored value when set (development). The key is absent-by-default. It MUST NOT be hardcoded, committed to the repository, shipped as a default, or printed in logs or the UI. The missing-key message MUST say where to obtain a key and that it is entered in Settings.

#### Scenario: Settings is the primary source
- **WHEN** the user saves a GIPHY API key in Settings and the environment variable is unset
- **THEN** the browser uses that stored key for requests

#### Scenario: Environment variable overrides
- **WHEN** `GIPHY_API_KEY` is set in the environment
- **THEN** that value is used even if Settings also has a key

#### Scenario: Key stays out of logs and the repo
- **WHEN** a GIPHY request is made
- **THEN** the key does not appear in log lines or on-screen copy, and no default key is shipped

#### Scenario: No API key explains where to enter one
- **WHEN** neither Settings nor the environment provides a key
- **THEN** the browser explains that a key is required, where to get one, and that it is entered in Settings, and does not send a request

### Requirement: GIPHY attribution
The GIPHY browser MUST display GIPHY attribution required of API consumers (a visible "Powered by GIPHY" mark on the browser).

#### Scenario: Attribution is visible while browsing
- **WHEN** the GIPHY browser is open
- **THEN** a Powered by GIPHY attribution is visible
