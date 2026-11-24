# Si funksionon kodi

## Rrjedha e një shkarkimi

```
UI (ui.py)                   Thread pune                     Downloader (downloader.py)
-----------                  -----------                     --------------------------
start()  ── kontrollon fushat, ruan cilësimet
         └─ nis thread ──▶   _work()
                               ├─ search() / expand_urls() ─▶ kthen listë Job
                               └─ run(jobs) ────────────────▶ ThreadPoolExecutor
                                                               └─ _download_one() × N
                                                                    ├─ extract_info (1 herë)
                                                                    ├─ kontrollon historikun
                                                                    └─ process_ie_result → MP3
_poll_events() ◀── queue ◀── on_task(TaskUpdate) / on_log(str)
  (çdo 100 ms, në thread-in kryesor)
```

### Rregulla e artë: Tkinter vetëm nga thread-i kryesor

Tkinter nuk është thread-safe. Thread-et e shkarkimit **nuk prekin kurrë widget-et**: ata vendosin ngjarje
në `App.events` (`queue.Queue`), dhe `_poll_events()` i lexon nga thread-i kryesor me `root.after(100, …)`.

Ngjarjet:

| Lloji | Payload | Çfarë bën |
|---|---|---|
| `task` | `TaskUpdate` | Përditëson rreshtin e këngës dhe progresin total |
| `log` | `str` | Shton rresht në log |
| `status` | `str` | Ndryshon tekstin mbi progress bar |
| `total` | `int` | Numri i këngëve në punë |
| `done` | `Summary` | Përfundim (ose ndalim) |
| `error` | `str` | Gabim që ndaloi gjithçka (p.sh. pa internet) |

### Statuset e një kënge

`Në pritje → Duke marrë info → Duke shkarkuar → Duke konvertuar → Përfundoi`
ose në fund: `Anashkaluar`, `Dështoi`, `Anuluar`.

Numëruesit (✓ » ✕) llogariten nga statuset, jo nga variabla të përbashkëta, ndaj s'ka race condition.

### Ndalimi

`Downloader.cancel()` vendos një `threading.Event`. Progress hook-u i yt-dlp hedh `DownloadCancelled`
në shkarkimin e radhës, dhe këngët që s'kanë filluar dalin menjëherë si *Anuluar*. Konvertimi me ffmpeg
që ka filluar lihet të përfundojë.

### ffmpeg

- Nga kodi: përdoret ffmpeg nga `PATH`.
- Nga `.exe`: PyInstaller e paketon te `ffmpeg/` brenda, dhe `config.FFMPEG_LOCATION` i tregon yt-dlp-së ku është.

### Postprocesorët (kur "Shto kopertinën" është aktiv)

1. `FFmpegThumbnailsConvertor` – kopertina në JPG (para shkarkimit)
2. `FFmpegExtractAudio` – në MP3 me cilësinë e zgjedhur
3. `FFmpegMetadata` – titulli, artisti, etj.
4. `EmbedThumbnail` – fut kopertinën në MP3

## Skedarët e të dhënave

`~/.music_downloader_history.json`:
```json
{ "<video_id>": { "title": "Titulli", "title_hash": "<md5 e titullit me shkronja të vogla>",
                  "downloaded_at": "2026-01-31 18:05:00" } }
```
Një këngë quhet "e shkarkuar" nëse përputhet ID-ja **ose** titulli.

`~/.music_downloader_settings.json`: fushat e `config.Settings`.

## Shtimi i një opsioni të ri

1. Shto fushën në `Settings` (`config.py`) me vlerë parazgjedhje.
2. Shto widget-in në `ui.py` dhe lexoje te `_save_settings()`.
3. Kaloje te `params` në `App.start()` dhe pranoje te `Downloader.run()` / `_ydl_opts()`.

## Logo

`tools/make_logo.py` e vizaton logon me Pillow (gradient, notë muzikore, distinktiv shkarkimi) dhe krijon:
`assets/logo.png` (512px), `assets/logo_64.png` (header), `assets/logo.ico` (16–256px, për .exe dhe dritaren),
`assets/check_on.png` / `check_off.png` (checkbox-et e UI).
