# Scrape Yearbook

Lightweight, unofficial tool to download **posts** and **gallery images** from the [IITB Yearbook portal](https://yearbook.sarc-iitb.org).

Not affiliated with SARC, IIT Bombay, or the Yearbook team.

## What you get

| Export | Contents |
|--------|----------|
| **PDF** | In-browser preview, optional gallery images embedded |
| **Markdown** | Post text + JSON; optional gallery images linked from the markdown file |

## Web app

```powershell
pip install -r requirements.txt
npm install
npm run build:css
python app.py
```

CSS uses [Tailwind](https://tailwindcss.com). After editing templates, rebuild with `npm run build:css` (or `npm run watch:css` while developing).

Open [http://127.0.0.1:5000](http://127.0.0.1:5000)

Production (no debug, custom port):

```powershell
$env:FLASK_DEBUG = "0"
$env:PORT = "8080"
python app.py
```

## CLI

```powershell
$env:YB_USERNAME = "yourroll@iitb.ac.in"
$env:YB_PASSWORD = "your-password"
python scrape_yearbook.py --profile-id 1234 --format both
```

| Flag | Description |
|------|-------------|
| `--username` | Roll or email (or `YB_USERNAME`) |
| `--password` | Password (or `YB_PASSWORD`) |
| `--profile-id` | Target profile; omit for your own |
| `--format` | `md`, `pdf`, or `both` (default) |
| `--no-gallery` | Skip image download |

## Project layout

```
├── scrape_yearbook.py   # Core scraper + export
├── app.py               # Flask web UI
├── static/css/input.css
├── static/css/tailwind.css
├── tailwind.config.js
├── package.json
├── static/js/theme.js
├── static/js/loader.js
├── templates/index.html
├── templates/result.html
├── requirements.txt
└── README.md
```

## Privacy

- Credentials are sent only to the official Yearbook API for a single request.
- Nothing is stored on disk beyond temporary export files in the system temp folder.

## Troubleshooting

- **Invalid credentials** — use `roll@iitb.ac.in`, verify password on the [portal](https://yearbook.sarc-iitb.org).
- **Profile ID** — number in `/profile/ID` when viewing someone's wall.
- **Gallery empty** — posts still export; some profiles have no gallery images.
