"""Rrugët e skedarëve dhe cilësimet që ruhen ndërmjet hapjeve."""

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Kur programi ekzekutohet si .exe (PyInstaller), skedarët janë të shpaketuar në sys._MEIPASS
FROZEN = getattr(sys, "frozen", False)
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def resource_path(*parts: str) -> Path:
    """Kthen rrugën e një skedari në projekt (ose brenda .exe)."""
    return BASE_DIR.joinpath(*parts)


# Në .exe, ffmpeg është i paketuar brenda; përndryshe përdoret ai në PATH
FFMPEG_LOCATION = str(resource_path("ffmpeg")) if FROZEN else None

LOGO_PNG = resource_path("assets", "logo.png")
LOGO_ICO = resource_path("assets", "logo.ico")

HISTORY_FILE = Path.home() / ".music_downloader_history.json"
SETTINGS_FILE = Path.home() / ".music_downloader_settings.json"

QUALITIES = ("128", "192", "256", "320")


@dataclass
class Settings:
    output_dir: str = str(Path.home() / "Downloads" / "Muzika")
    last_query: str = ""
    num_songs: int = 10
    parallel: int = 4
    quality: str = "192"
    skip_duplicates: bool = True
    embed_metadata: bool = True

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        try:
            settings = cls(**known)
        except TypeError:
            return cls()
        if settings.quality not in QUALITIES:
            settings.quality = "192"
        return settings

    def save(self) -> None:
        try:
            SETTINGS_FILE.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
