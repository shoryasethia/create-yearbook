<p align="center">
  <img src="static/logo.png" width="100" alt="Create Yearbook logo" />
</p>

<h1 align="center">Create Yearbook</h1>

<p align="center">
  Unofficial tool to export your <a href="https://yearbook.sarc-iitb.org">IITB Yearbook</a> posts and gallery as PDF or Markdown.<br>
  Runs entirely on your machine — no cloud, no data stored.
</p>
---

## What you get

| Export | Contents |
|--------|----------|
| **PDF** | All posts for/by you, optional gallery images embedded |
| **Markdown** | Post text + JSON metadata; gallery images bundled as a zip |

---

## Setup

```bash
pip install -r requirements.txt
npm install && npm run build:css
```

---

## Web app

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000), enter your roll number and yearbook password, and export.

---

## CLI

```bash
python scrape_yearbook.py --username 22b1234@iitb.ac.in --password yourpassword
```

Via environment variables:

```bash
export YB_USERNAME=22b1234@iitb.ac.in
export YB_PASSWORD=yourpassword
python scrape_yearbook.py --profile-id 1234 --format both
```

| Flag | Default | Description |
|------|---------|-------------|
| `--username` | `YB_USERNAME` | Roll number or `roll@iitb.ac.in` |
| `--password` | `YB_PASSWORD` | Yearbook portal password |
| `--profile-id` | your own profile | Number from `/profile/1234` in the URL |
| `--format` | `both` | `md`, `pdf`, or `both` |
| `--no-gallery` | off | Skip gallery image download |

---

## Project layout

```
├── app.py                  # Flask web UI
├── scrape_yearbook.py      # Scraper + PDF/Markdown exporter
├── requirements.txt
├── package.json            # Tailwind CSS build
├── static/
│   ├── css/input.css
│   ├── css/tailwind.css
│   └── js/
└── templates/
```

---

## Privacy

- Credentials go directly to the official Yearbook API and are never stored.
- Exported files live in your OS temp folder and are cleaned up automatically.
- No analytics, no servers, no third-party calls.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Invalid credentials | Use the password set on the **yearbook portal**, not your IITB SSO password |
| Profile ID | Copy the number from `/profile/1234` when viewing someone's wall |
| Gallery empty | Some profiles have no gallery — posts still export fine |
| CSS broken | Run `npm install && npm run build:css` |

---

## License

[Apache 2.0](LICENSE) · made by [Shorya Sethia](https://github.com/shoryasethia)
