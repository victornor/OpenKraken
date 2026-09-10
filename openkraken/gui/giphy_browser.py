"""GIPHY search dialog for picking an LCD GIF background."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openkraken.backend import giphy

if TYPE_CHECKING:
    from openkraken.config import AppConfig

_LOGGER = logging.getLogger(__name__)

_GIF_FILTER = "Animated GIF (*.gif)"
_PREVIEW_PX = 120
_COLUMNS = 4


class _GiphyWorker(QThread):
    """Runs search/trending/download off the UI thread."""

    listed = pyqtSignal(object)  # list[giphy.GiphyGif] plus local preview paths
    failed = pyqtSignal(str, str)  # kind, message
    downloaded = pyqtSignal(str)  # local original path
    categories = pyqtSignal(object)  # list[str]

    def __init__(
        self,
        mode: str,
        api_key: str,
        query: str = "",
        gif: giphy.GiphyGif | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._api_key = api_key
        self._query = query
        self._gif = gif

    def run(self) -> None:
        try:
            if self._mode == "categories":
                self.categories.emit(giphy.categories(self._api_key))
                return
            if self._mode == "download" and self._gif is not None:
                path = giphy.download_gif(self._gif, self._api_key)
                self.downloaded.emit(str(path))
                return
            if self._mode == "trending" or not self._query.strip():
                items = giphy.trending(self._api_key)
            else:
                items = giphy.search(self._query.strip(), self._api_key)
            previews: list[tuple[giphy.GiphyGif, str]] = []
            for item in items:
                try:
                    preview = giphy.cache_preview(item, self._api_key)
                    previews.append((item, str(preview)))
                except giphy.GiphyError:
                    continue
            self.listed.emit(previews)
        except giphy.GiphyError as exc:
            self.failed.emit(exc.kind, exc.message)
        except Exception:
            _LOGGER.exception("GIPHY worker failed")
            self.failed.emit("http", "GIPHY request failed.")


class GiphyBrowserDialog(QDialog):
    """Search, browse trending, and pick a GIF. Local file remains available."""

    def __init__(self, config: "AppConfig", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.chosen_path: str = ""
        self.setWindowTitle("Choose GIF")
        self.resize(640, 520)

        root = QVBoxLayout(self)
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search GIPHY")
        self._search.textChanged.connect(self._on_query_changed)
        search_row.addWidget(self._search, stretch=1)
        self._category = QComboBox()
        self._category.addItem("Trending")
        self._category.currentTextChanged.connect(self._on_category)
        search_row.addWidget(self._category)
        local_btn = QPushButton("Choose file…")
        local_btn.clicked.connect(self._choose_local)
        search_row.addWidget(local_btn)
        root.addLayout(search_row)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setProperty("hint", True)
        root.addWidget(self._status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(8)
        self._scroll.setWidget(self._grid_host)
        root.addWidget(self._scroll, stretch=1)

        attr = QLabel("Powered by GIPHY")
        attr.setAlignment(Qt.AlignmentFlag.AlignRight)
        attr.setProperty("hint", True)
        root.addWidget(attr)

        self._movies: list[QMovie] = []
        self._worker: _GiphyWorker | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._run_search)

        key = giphy.resolve_api_key(getattr(config, "giphy_api_key", ""))
        if not key:
            self._status.setText(giphy.MISSING_KEY_MESSAGE)
        else:
            self._load_categories()
            self._run_search()

    def _api_key(self) -> str:
        return giphy.resolve_api_key(getattr(self._config, "giphy_api_key", ""))

    def _on_query_changed(self, _text: str) -> None:
        self._debounce.start()

    def _on_category(self, name: str) -> None:
        if name == "Trending":
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
            self._run_search()
            return
        self._search.setText(name)

    def _load_categories(self) -> None:
        key = self._api_key()
        if not key:
            return
        worker = _GiphyWorker("categories", key, parent=self)
        worker.categories.connect(self._on_categories)
        worker.failed.connect(lambda _k, _m: None)
        worker.start()
        self._cat_worker = worker

    def _on_categories(self, names: object) -> None:
        self._category.blockSignals(True)
        current = self._category.currentText()
        self._category.clear()
        self._category.addItem("Trending")
        for name in names or []:
            if isinstance(name, str) and name:
                self._category.addItem(name)
        idx = self._category.findText(current)
        self._category.setCurrentIndex(max(0, idx))
        self._category.blockSignals(False)

    def _run_search(self) -> None:
        key = self._api_key()
        if not key:
            self._status.setText(giphy.MISSING_KEY_MESSAGE)
            self._clear_grid()
            return
        if self._worker is not None and self._worker.isRunning():
            return
        query = self._search.text().strip()
        mode = "trending" if not query else "search"
        self._status.setText("Loading…")
        worker = _GiphyWorker(mode, key, query=query, parent=self)
        worker.listed.connect(self._on_listed)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_listed(self, previews: object) -> None:
        items: list[tuple[giphy.GiphyGif, str]] = previews  # type: ignore[assignment]
        self._clear_grid()
        if not items:
            self._status.setText("No GIFs matched.")
            return
        self._status.setText("")
        for i, (gif, path) in enumerate(items):
            cell = QLabel()
            cell.setFixedSize(_PREVIEW_PX, _PREVIEW_PX)
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setCursor(Qt.CursorShape.PointingHandCursor)
            cell.setToolTip(gif.title)
            movie = QMovie(path)
            movie.setScaledSize(cell.size())
            cell.setMovie(movie)
            movie.start()
            self._movies.append(movie)
            cell.mousePressEvent = lambda _e, g=gif: self._select(g)  # type: ignore[method-assign]
            self._grid.addWidget(cell, i // _COLUMNS, i % _COLUMNS)

    def _on_failed(self, kind: str, message: str) -> None:
        self._status.setText(message or kind)

    def _select(self, gif: giphy.GiphyGif) -> None:
        key = self._api_key()
        if not key:
            self._status.setText(giphy.MISSING_KEY_MESSAGE)
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._status.setText("Downloading…")
        worker = _GiphyWorker("download", key, gif=gif, parent=self)
        worker.downloaded.connect(self._on_downloaded)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_downloaded(self, path: str) -> None:
        self.chosen_path = path
        self.accept()

    def _choose_local(self) -> None:
        path, _sel = QFileDialog.getOpenFileName(self, "Choose GIF", "", _GIF_FILTER)
        if path:
            self.chosen_path = path
            self.accept()

    def _clear_grid(self) -> None:
        for movie in self._movies:
            movie.stop()
        self._movies.clear()
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
