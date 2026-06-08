# Create Yearbook

Lightweight, unofficial tool to export **posts** and **gallery images** from the [IITB Yearbook portal](https://yearbook.sarc-iitb.org) as a PDF or Markdown file.

> **Not affiliated with SARC, IIT Bombay, or the Yearbook team.**

---

## ⚠️ Run locally only

The yearbook portal is protected by Cloudflare and blocks requests from cloud servers (Render, Vercel, Railway, etc.). This tool works **only when run on your own machine** using your regular internet connection.

---

## What you get

| Export | Contents |
|--------|----------|
| **PDF** | In-browser preview, all posts, optional gallery images embedded |
| **Markdown** | Post text + JSON metadata; optional gallery images bundled as a zip |

---

## Setup

```bash
pip install -r requirements.txt
npm install
npm run build:css
```

---

## Web app

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

Enter your roll number (or `roll@iitb.ac.in`) and your **yearbook portal password** — not your IITB LDAP/SSO password, but the one you set on the portal itself.

---

## CLI

```bash
python scrape_yearbook.py --username 22b1234@iitb.ac.in --password yourpassword
```

Or use environment variables:

```bash
export YB_USERNAME=22b1234@iitb.ac.in
export YB_PASSWORD=yourpassword
python scrape_yearbook.py --profile-id 1234 --format both
```

| Flag | Default | Description |
|------|---------|-------------|
| `--username` | `YB_USERNAME` env | Roll or email |
| `--password` | `YB_PASSWORD` env | Yearbook portal password |
| `--profile-id` | your own | Profile number from `/profile/ID` in the URL |
| `--format` | `both` | `md`, `pdf`, or `both` |
| `--no-gallery` | off | Skip downloading gallery images |

---

## Project layout

```
├── app.py                  # Flask web UI
├── scrape_yearbook.py      # Core scraper + PDF/Markdown exporter
├── requirements.txt
├── package.json            # Tailwind CSS build
├── tailwind.config.js
├── static/
│   ├── css/
│   │   ├── input.css
│   │   └── tailwind.css    # compiled, committed
│   └── js/
│       ├── loader.js
│       ├── share.js
│       ├── theme.js
│       └── wakeup.js
└── templates/
    ├── index.html
    ├── result.html
    ├── _topbar.html
    ├── _footer.html
    └── _wake_overlay.html
```

---

## Privacy

- Credentials are sent directly to the official Yearbook API and are not stored anywhere.
- Export files are written to your system's temp folder and deleted when the OS cleans it up.
- No analytics, no logging, no third-party services.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Invalid credentials | Use the password set on the yearbook portal, not your IITB LDAP password |
| Profile ID | Copy the number from `/profile/1234` in the URL when viewing someone's wall |
| Gallery empty | Some profiles have no gallery images — posts still export |
| CSS looks broken | Run `npm install && npm run build:css` |

---

## License

[Apache 2.0](LICENSE) — made by [Shorya Sethia](https://github.com/shoryasethia)
