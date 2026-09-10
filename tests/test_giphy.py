"""Offline GIPHY client tests with mocked HTTP."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openkraken.backend import giphy


class _Resp:
    def __init__(self, payload) -> None:
        if isinstance(payload, (bytes, bytearray)):
            self._body = bytes(payload)
        else:
            self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _gif_payload(n: int = 2) -> dict:
    items = []
    for i in range(n):
        items.append(
            {
                "id": f"id{i}",
                "title": f"gif {i}",
                "images": {
                    "fixed_width_small": {"url": f"https://example.test/p{i}.gif"},
                    "downsized": {"url": f"https://example.test/d{i}.gif"},
                },
            }
        )
    return {"data": items}


class GiphyClientTest(unittest.TestCase):
    def test_missing_key_does_not_request(self) -> None:
        calls: list[int] = []

        def boom(*_a, **_k):
            calls.append(1)
            raise AssertionError("must not request")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIPHY_API_KEY", None)
            with patch("urllib.request.urlopen", boom):
                with self.assertRaises(giphy.GiphyError) as ctx:
                    giphy.search("cats", "")
        self.assertEqual(ctx.exception.kind, "missing_key")
        self.assertIn("Settings", ctx.exception.message)
        self.assertIn("developers.giphy.com", ctx.exception.message)
        self.assertEqual(calls, [])

    def test_env_overrides_settings(self) -> None:
        with patch.dict(os.environ, {"GIPHY_API_KEY": "envkey"}):
            self.assertEqual(giphy.resolve_api_key("cfgkey"), "envkey")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIPHY_API_KEY", None)
            self.assertEqual(giphy.resolve_api_key("cfgkey"), "cfgkey")

    def test_search_success_and_empty(self) -> None:
        with patch("urllib.request.urlopen", lambda *_a, **_k: _Resp(_gif_payload(2))):
            items = giphy.search("cats", "k")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].id, "id0")
        with patch("urllib.request.urlopen", lambda *_a, **_k: _Resp({"data": []})):
            self.assertEqual(giphy.search("zzz", "k"), [])

    def test_rate_limited(self) -> None:
        def boom(req, timeout=None):
            raise HTTPError("https://api.giphy.com/v1/gifs/search", 429, "no", hdrs=None, fp=io.BytesIO())

        with patch("urllib.request.urlopen", boom):
            with self.assertRaises(giphy.GiphyError) as ctx:
                giphy.trending("k")
        self.assertEqual(ctx.exception.kind, "rate_limited")

    def test_network_error(self) -> None:
        def boom(req, timeout=None):
            raise URLError("down")

        with patch("urllib.request.urlopen", boom):
            with self.assertRaises(giphy.GiphyError) as ctx:
                giphy.trending("k")
        self.assertEqual(ctx.exception.kind, "network")

    def test_client_does_not_log_the_key(self) -> None:
        import logging

        records: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda rec: records.append(rec.getMessage())  # type: ignore[method-assign]
        log = logging.getLogger("openkraken.backend.giphy")
        log.addHandler(handler)
        log.setLevel(logging.DEBUG)
        try:
            with patch("urllib.request.urlopen", lambda *_a, **_k: _Resp(_gif_payload(1))):
                giphy.search("cats", "super-secret-key-value")
        finally:
            log.removeHandler(handler)
        blob = " ".join(records)
        self.assertNotIn("super-secret-key-value", blob)

    def test_preview_cache_hit_skips_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gif = giphy.GiphyGif(
                "abc", "t", "https://example.test/p.gif", "https://example.test/d.gif"
            )
            dest = root / "giphy-preview" / "abc.gif"
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b"GIF89a")
            calls: list[int] = []

            def boom(*_a, **_k):
                calls.append(1)
                raise AssertionError("must not download")

            with patch("urllib.request.urlopen", boom):
                path = giphy.cache_preview(gif, "k", media_dir=root)
            self.assertEqual(path, dest)
            self.assertEqual(calls, [])

    def test_engine_module_does_not_import_giphy(self) -> None:
        import inspect

        from openkraken.backend import engine as eng

        self.assertNotIn("giphy", inspect.getsource(eng))


if __name__ == "__main__":
    unittest.main()
