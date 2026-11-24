# Ndryshimet

## 2.0.0

### E re
- Logo dhe ikonë për programin dhe `.exe`-në.
- Dizajn i ri i errët, me hapa të qartë: 1 Çfarë → 2 Cilësimet → 3 Ku.
- Skeda të veçanta për *Kërko* dhe *Link-e / Playlist*. Më parë programi hamendësonte nga kutia e tekstit.
- Mbështetje për playlist-a.
- Zgjedhja e cilësisë (128 / 192 / 256 / 320 kbps).
- Kopertina, titulli dhe artisti futen në MP3.
- Butoni **Ndalo**.
- Butoni **Hap dosjen**, dhe pyetja "Të hap dosjen?" në fund.
- Progres i vërtetë (%) për çdo këngë dhe për totalin. Përqindja shfaqet edhe në titullin e dritares.
- Dy klikime mbi një këngë të dështuar tregojnë arsyen.
- Cilësimet ruhen ndërmjet hapjeve.
- Tekst i qartë në ekrane me shkallëzim (125%, 150%).

### Rregullime
- Programi mund të ngecte ose të rrëzohej, sepse thread-et e shkarkimit prekin UI-në direkt. Tani komunikojnë me radhë (queue).
- Çdo video merrej dy herë nga YouTube. Tani merret një herë, prandaj fillon më shpejt.
- Numëruesit (përfunduar/dështuar) mund të dilnin gabim kur shkarkonin disa thread-e njëkohësisht.
- Historiku mund të prishej kur ruhej nga disa thread-e njëkohësisht.
- "Pastro historikun" e rinisnte gjithë programin. Tani thjesht përditëson numrin.
- Totali tregonte numrin e kërkuar edhe kur YouTube kthente më pak këngë.
- Në `.exe` pa konsolë, gabimet e yt-dlp mund të rrëzonin programin.

### Struktura
- Kodi u nda në `shkarkues/` (config, history, downloader, ui). Logjika e shkarkimit nuk varet më nga UI.
- `build.ps1` për ndërtimin e `.exe`-së me një komandë.

## 1.0.0
- Versioni i parë: kërkim, shkarkim paralel, historik.
