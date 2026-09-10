"""GIPHY API client for the LCD GIF browser.

Stdlib ``urllib`` only. The API key comes from Settings (``config_key``) with
an optional ``GIPHY_API_KEY`` environment override. The key is never logged.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from openkraken.config import MEDIA_DIR

_LOGGER = logging.getLogger(__name__)

ENV_NAME = "GIPHY_API_KEY"
DEVELOPERS_URL = "https://developers.giphy.com/"
_API = "https://api.giphy.com/v1"
_TIMEOUT = 8.0
_UA = "OpenKraken-giphy"
_RATING = "pg-13"
_LIMIT = 24
MISSING_KEY_MESSAGE = (
    "No GIPHY API key. Get one at https://developers.giphy.com/ and enter it "
    "in Settings, or set the GIPHY_API_KEY environment variable."
)


class GiphyError(Exception):
    """Mapped GIPHY failure. ``kind`` is missing_key / network / rate_limited / http."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class GiphyGif:
    """One search/trending result."""

    id: str
    title: str
    preview_url: str
    download_url: str


def resolve_api_key(config_key: str = "") -> str:
    """Return the env override if set, otherwise the Settings value."""
    env = os.environ.get(ENV_NAME, "").strip()
    if env:
        return env
    return (config_key or "").strip()


def search(query: str, api_key: str, *, offset: int = 0) -> list[GiphyGif]:
    """Search GIPHY. Empty query is not sent; use :func:`trending`."""
    data = _get(
        "/gifs/search",
        api_key,
        {"q": query, "limit": str(_LIMIT), "offset": str(offset), "rating": _RATING},
    )
    return _parse_gifs(data)


def trending(api_key: str, *, offset: int = 0) -> list[GiphyGif]:
    """Trending GIFs."""
    data = _get(
        "/gifs/trending",
        api_key,
        {"limit": str(_LIMIT), "offset": str(offset), "rating": _RATING},
    )
    return _parse_gifs(data)


def categories(api_key: str) -> list[str]:
    """Category names for browse chips. Empty list if the payload is odd."""
    data = _get("/gifs/categories", api_key, {})
    names: list[str] = []
    for item in data.get("data") or []:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return names


def download_gif(gif: GiphyGif, api_key: str, media_dir: Path | None = None) -> Path:
    """Download *gif* to ``media/giphy/<id>.gif`` and return the path."""
    root = Path(media_dir) if media_dir is not None else MEDIA_DIR
    dest = root / "giphy" / f"{gif.id}.gif"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _download(gif.download_url, dest, api_key)
    return dest


def cache_preview(gif: GiphyGif, api_key: str, media_dir: Path | None = None) -> Path:
    """Download a small preview GIF if missing; return the local path."""
    root = Path(media_dir) if media_dir is not None else MEDIA_DIR
    dest = root / "giphy-preview" / f"{gif.id}.gif"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    _download(gif.preview_url, dest, api_key)
    return dest


def _require_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if not key:
        raise GiphyError("missing_key", MISSING_KEY_MESSAGE)
    return key


def _get(path: str, api_key: str, params: dict[str, str]) -> dict:
    key = _require_key(api_key)
    query = dict(params)
    query["api_key"] = key
    url = f"{_API}{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _LOGGER.info("GIPHY %s failed: HTTP %s", path, exc.code)
        if exc.code == 429:
            raise GiphyError("rate_limited", "GIPHY rate limit reached. Try again later.") from exc
        raise GiphyError("http", f"GIPHY request failed (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        _LOGGER.info("GIPHY %s failed: network error", path)
        raise GiphyError("network", "Could not reach GIPHY. Check your network.") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        _LOGGER.info("GIPHY %s failed: bad JSON", path)
        raise GiphyError("http", "GIPHY returned an unexpected response.") from exc
    if not isinstance(payload, dict):
        raise GiphyError("http", "GIPHY returned an unexpected response.")
    return payload


def _parse_gifs(payload: dict) -> list[GiphyGif]:
    out: list[GiphyGif] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        gif_id = item.get("id")
        if not isinstance(gif_id, str) or not gif_id:
            continue
        images = item.get("images") if isinstance(item.get("images"), dict) else {}
        preview = _pick_url(images, ("fixed_width_small", "preview_gif", "fixed_width"))
        download = _pick_url(images, ("downsized", "original", "downsized_medium"))
        if not preview or not download:
            continue
        title = item.get("title") if isinstance(item.get("title"), str) else ""
        out.append(GiphyGif(id=gif_id, title=title or gif_id, preview_url=preview, download_url=download))
    return out


def _pick_url(images: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        block = images.get(key)
        if isinstance(block, dict):
            url = block.get("url")
            if isinstance(url, str) and url.startswith("http"):
                return url
    return ""


def _download(url: str, dest: Path, api_key: str) -> None:
    _require_key(api_key)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp, open(dest, "wb") as fh:
            fh.write(resp.read())
    except urllib.error.HTTPError as exc:
        _LOGGER.info("GIPHY download failed: HTTP %s", exc.code)
        if exc.code == 429:
            raise GiphyError("rate_limited", "GIPHY rate limit reached. Try again later.") from exc
        raise GiphyError("http", "Could not download that GIF.") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        _LOGGER.info("GIPHY download failed: network error")
        raise GiphyError("network", "Could not reach GIPHY. Check your network.") from exc
