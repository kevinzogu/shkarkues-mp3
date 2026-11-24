"""Historiku i këngëve të shkarkuara, që të mos shkarkohen dy herë."""

import hashlib
import json
import threading
import time
from pathlib import Path

from .config import HISTORY_FILE


class History:
    """Ruan {video_id: {title, title_hash, downloaded_at}} në një skedar JSON.

    E sigurt për përdorim nga disa thread-e njëkohësisht.
    """

    def __init__(self, path: Path = HISTORY_FILE):
        self.path = path
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_locked(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    @staticmethod
    def _title_hash(title: str) -> str:
        return hashlib.md5(title.lower().encode()).hexdigest()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def contains(self, video_id: str, title: str) -> bool:
        title_hash = self._title_hash(title)
        with self._lock:
            if video_id and video_id in self._data:
                return True
            return any(
                isinstance(info, dict) and info.get("title_hash") == title_hash
                for info in self._data.values()
            )

    def add(self, video_id: str, title: str) -> None:
        with self._lock:
            self._data[video_id or self._title_hash(title)] = {
                "title": title,
                "title_hash": self._title_hash(title),
                "downloaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_locked()

    def clear(self) -> None:
        with self._lock:
            self._data = {}
            self._save_locked()
