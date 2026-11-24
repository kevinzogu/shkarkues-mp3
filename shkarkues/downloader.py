"""Logjika e kërkimit dhe shkarkimit (pa asnjë kod UI).

UI merr njoftime përmes dy callback-eve:
  on_task(TaskUpdate)  - ndryshim statusi/progresi për një këngë
  on_log(str)          - mesazh për log-un
Callback-et thirren nga thread-e pune, ndaj UI duhet t'i kalojë në thread-in kryesor.
"""

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadCancelled

from .config import FFMPEG_LOCATION
from .history import History


class Status(str, Enum):
    WAITING = "Në pritje"
    FETCHING = "Duke marrë info"
    DOWNLOADING = "Duke shkarkuar"
    CONVERTING = "Duke konvertuar"
    DONE = "Përfundoi"
    SKIPPED = "Anashkaluar"
    FAILED = "Dështoi"
    CANCELLED = "Anuluar"


@dataclass
class Job:
    url: str
    title: str = ""


@dataclass
class TaskUpdate:
    index: int
    status: Status
    title: str = ""
    percent: float | None = None
    speed: str = ""
    eta: str = ""
    error: str = ""


@dataclass
class Summary:
    total: int = 0
    counts: dict = field(default_factory=lambda: {s: 0 for s in Status})

    @property
    def completed(self) -> int:
        return self.counts[Status.DONE]

    @property
    def skipped(self) -> int:
        return self.counts[Status.SKIPPED]

    @property
    def failed(self) -> int:
        return self.counts[Status.FAILED]

    @property
    def cancelled(self) -> int:
        return self.counts[Status.CANCELLED]


class _SilentLogger:
    """yt-dlp shkruan në stderr; në .exe pa konsolë kjo s'ka kuptim. Gabimet vijnë si exception."""

    def debug(self, msg):
        pass

    info = warning = error = debug


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def clean_error(exc: Exception) -> str:
    msg = _ANSI.sub("", str(exc)).strip()
    msg = re.sub(r"^ERROR:\s*", "", msg)
    msg = re.sub(r"^\[[^\]]+\]\s*[\w-]+:\s*", "", msg)  # "[youtube] abc123: ..."
    return msg.splitlines()[0] if msg else "Gabim i panjohur"


def _base_opts() -> dict:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "logger": _SilentLogger()}
    if FFMPEG_LOCATION:
        opts["ffmpeg_location"] = FFMPEG_LOCATION
    return opts


def _is_playlist(url: str) -> bool:
    return "/playlist?" in url or ("list=" in url and "watch?v=" not in url)


class Downloader:
    def __init__(
        self,
        history: History,
        on_task: Callable[[TaskUpdate], None],
        on_log: Callable[[str], None],
    ):
        self.history = history
        self.on_task = on_task
        self.on_log = on_log
        self._cancel = threading.Event()

    # ---------- Kërkimi / përgatitja e listës ----------

    def search(self, query: str, max_results: int) -> list[Job]:
        opts = {**_base_opts(), "extract_flat": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        return [
            Job(f"https://www.youtube.com/watch?v={e['id']}", e.get("title") or "")
            for e in (result or {}).get("entries") or []
            if e and e.get("id")
        ]

    def expand_urls(self, urls: list[str]) -> list[Job]:
        """Kthen link-et në punë; playlist-at hapen në këngë të veçanta."""
        jobs: list[Job] = []
        seen: set[str] = set()
        for url in urls:
            if self._cancel.is_set():
                break
            if _is_playlist(url):
                self.on_log(f"Duke hapur playlist-ën: {url}")
                try:
                    opts = {**_base_opts(), "extract_flat": "in_playlist"}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=False) or {}
                    entries = [e for e in info.get("entries") or [] if e and e.get("id")]
                    self.on_log(f"Playlist-a '{info.get('title', '')}' ka {len(entries)} këngë")
                    new = [
                        Job(f"https://www.youtube.com/watch?v={e['id']}", e.get("title") or "")
                        for e in entries
                    ]
                except Exception as e:  # noqa: BLE001 - raportohet te përdoruesi
                    self.on_log(f"Nuk u hap playlist-a: {clean_error(e)}")
                    continue
            else:
                new = [Job(url)]
            for job in new:
                if job.url not in seen:
                    seen.add(job.url)
                    jobs.append(job)
        return jobs

    # ---------- Shkarkimi ----------

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def reset(self) -> None:
        self._cancel.clear()

    def run(
        self,
        jobs: list[Job],
        output_dir: str,
        quality: str = "192",
        parallel: int = 4,
        skip_duplicates: bool = True,
        embed_metadata: bool = True,
    ) -> Summary:
        os.makedirs(output_dir, exist_ok=True)
        summary = Summary(total=len(jobs))
        for i, job in enumerate(jobs, 1):
            self.on_task(TaskUpdate(i, Status.WAITING, job.title or job.url))

        settings = dict(
            output_dir=output_dir,
            quality=quality,
            skip_duplicates=skip_duplicates,
            embed_metadata=embed_metadata,
        )
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            futures = [
                pool.submit(self._download_one, i, job, **settings)
                for i, job in enumerate(jobs, 1)
            ]
            for future in as_completed(futures):
                summary.counts[future.result()] += 1
        return summary

    def _ydl_opts(self, output_dir, quality, embed_metadata, progress_hook, pp_hook) -> dict:
        postprocessors = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality}
        ]
        opts = {
            **_base_opts(),
            "format": "bestaudio/best",
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "noplaylist": True,
            "windowsfilenames": True,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [pp_hook],
        }
        if embed_metadata:
            opts["writethumbnail"] = True
            postprocessors = [
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
                *postprocessors,
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail"},
            ]
        opts["postprocessors"] = postprocessors
        return opts

    def _download_one(
        self, index: int, job: Job, output_dir: str, quality: str,
        skip_duplicates: bool, embed_metadata: bool,
    ) -> Status:
        title = job.title or job.url

        def emit(status: Status, **kw) -> None:
            self.on_task(TaskUpdate(index, status, title, **kw))

        if self._cancel.is_set():
            emit(Status.CANCELLED)
            return Status.CANCELLED

        def progress_hook(d):
            if self._cancel.is_set():
                raise DownloadCancelled()
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                pct = d.get("downloaded_bytes", 0) / total * 100 if total else None
                emit(
                    Status.DOWNLOADING,
                    percent=pct,
                    speed=_ANSI.sub("", d.get("_speed_str", "")).strip(),
                    eta=_ANSI.sub("", d.get("_eta_str", "")).strip(),
                )

        def pp_hook(d):
            if d["status"] == "started" and d.get("postprocessor") == "ExtractAudio":
                emit(Status.CONVERTING, percent=100)

        emit(Status.FETCHING)
        try:
            opts = self._ydl_opts(output_dir, quality, embed_metadata, progress_hook, pp_hook)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job.url, download=False)
                title = info.get("title") or title
                video_id = info.get("id", "")

                if skip_duplicates and self.history.contains(video_id, title):
                    emit(Status.SKIPPED, eta="Ekziston")
                    self.on_log(f"Anashkaluar (e shkarkuar më parë): {title}")
                    return Status.SKIPPED

                emit(Status.DOWNLOADING, percent=0)
                ydl.process_ie_result(info, download=True)

            self.history.add(video_id, title)
            emit(Status.DONE, percent=100)
            self.on_log(f"U shkarkua: {title}")
            return Status.DONE
        except Exception as e:  # noqa: BLE001 - çdo gabim raportohet për këngën
            if self._cancel.is_set():
                emit(Status.CANCELLED)
                return Status.CANCELLED
            err = clean_error(e)
            emit(Status.FAILED, error=err)
            self.on_log(f"Dështoi: {title} - {err}")
            return Status.FAILED
