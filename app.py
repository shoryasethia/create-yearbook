import json

import os

import re

import tempfile

import uuid

from pathlib import Path



from dotenv import load_dotenv

from flask import Flask, abort, flash, make_response, redirect, render_template, request, send_file, url_for



from scrape_yearbook import (

    YearbookClient,

    build_markdown_bundle,

    export_json,

    export_markdown,

    export_pdf,

)



load_dotenv()



app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY") or uuid.uuid4().hex



GITHUB_REPO = os.environ.get("GITHUB_REPO", "https://github.com/shoryasethia/create-yearbook")

BACKEND_URL = os.environ.get("BACKEND_URL", "").rstrip("/")





def _env_bool(*keys: str) -> bool:

    for key in keys:

        if os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on"):

            return True

    return False





DEPRECATED_MODE = _env_bool("DEPRECATED_MODE", "DEPERECEATED_MODE")
BACKEND_ONLY = _env_bool("BACKEND_ONLY")



OUTPUT_DIR = Path(tempfile.gettempdir()) / "scrape-yearbook"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)





@app.context_processor

def inject_config():

    return {"github_repo": GITHUB_REPO}





@app.before_request

def enforce_deprecated_mode():

    if not DEPRECATED_MODE:

        return None

    if request.endpoint in ("health", "static", "wake"):

        return None

    return render_template("deprecated.html"), 503


@app.before_request
def enforce_backend_only_mode():

    if not BACKEND_ONLY:

        return None

    # Keep API-like/export endpoints available for the frontend app.
    if request.endpoint in ("health", "export", "download", "preview_pdf", "static"):

        return None

    # Block UI pages on backend deployment.
    if request.endpoint in ("index", "result", "wake"):

        abort(404)

    return None





def _slug(name: str) -> str:

    return re.sub(r"[^\w\-]+", "_", name.lower()).strip("_") or "yearbook"





def _job_dir(job_id: str) -> Path:

    return OUTPUT_DIR / job_id





def _load_meta(job_id: str) -> dict:

    meta_path = _job_dir(job_id) / "meta.json"

    if not meta_path.is_file():

        abort(404)

    return json.loads(meta_path.read_text(encoding="utf-8"))





def _create_export(data, export_format: str) -> str:

    job_id = uuid.uuid4().hex[:12]

    job_dir = _job_dir(job_id)

    job_dir.mkdir(parents=True)



    slug = _slug(data.name)

    meta = {

        "job_id": job_id,

        "name": data.name,

        "slug": slug,

        "format": export_format,

        "posts_for": len(data.posts_for),

        "posts_by": len(data.posts_by),

        "images": len(data.gallery_images),

        "has_pdf": False,

        "has_md": False,

        "md_with_images": False,

    }



    if export_format == "pdf":

        export_pdf(data, job_dir / "yearbook.pdf")

        meta["has_pdf"] = True

    else:

        markdown = export_markdown(data)

        (job_dir / "yearbook.md").write_text(markdown, encoding="utf-8")

        (job_dir / "yearbook.json").write_text(export_json(data), encoding="utf-8")

        meta["has_md"] = True

        if data.gallery_images:

            (job_dir / "export.bundle").write_bytes(build_markdown_bundle(data, markdown))

            meta["md_with_images"] = True



    (job_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    return job_id





@app.route("/health", methods=["GET", "OPTIONS"])

def health():

    if request.method == "OPTIONS":

        resp = make_response("", 204)

    elif DEPRECATED_MODE:

        resp = make_response({"status": "deprecated"}, 503)

    else:

        resp = make_response({"status": "ok"}, 200)

    resp.headers["Access-Control-Allow-Origin"] = "*"

    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"

    resp.headers["Access-Control-Allow-Headers"] = "Accept"

    return resp





@app.route("/wake")

def wake():

    if DEPRECATED_MODE:

        return render_template("deprecated.html"), 503

    return render_template("wake.html")





@app.route("/", methods=["GET"])

def index():

    return render_template("index.html")





@app.route("/export", methods=["POST"])

def export():

    username = request.form.get("username", "").strip()

    password = request.form.get("password", "")

    profile_raw = request.form.get("profile_id", "").strip()

    export_format = request.form.get("format", "pdf")

    if export_format not in ("pdf", "md"):

        export_format = "pdf"



    include_gallery = request.form.get("include_gallery") == "on"



    if not username or not password:

        flash("Username and password are required.")

        return redirect(url_for("index"))



    profile_id = None

    if profile_raw:

        try:

            profile_id = int(profile_raw)

        except ValueError:

            flash("Profile ID must be a number from the profile URL (/profile/ID).")

            return redirect(url_for("index"))



    try:

        client = YearbookClient(username, password)

        data = client.fetch(profile_id=profile_id, include_gallery=include_gallery)

    except ValueError as exc:

        flash(str(exc))

        return redirect(url_for("index"))

    except Exception:

        flash("Could not reach Yearbook. Check your connection and try again.")

        return redirect(url_for("index"))



    job_id = _create_export(data, export_format)

    return redirect(url_for("result", job_id=job_id))





@app.route("/result/<job_id>")

def result(job_id: str):

    meta = _load_meta(job_id)

    return render_template("result.html", meta=meta)





@app.route("/preview/<job_id>")

def preview_pdf(job_id: str):

    meta = _load_meta(job_id)

    if not meta.get("has_pdf"):

        abort(404)

    pdf_path = _job_dir(job_id) / "yearbook.pdf"

    if not pdf_path.is_file():

        abort(404)

    return send_file(pdf_path, mimetype="application/pdf")





@app.route("/download/<job_id>/<kind>")

def download(job_id: str, kind: str):

    meta = _load_meta(job_id)

    job_dir = _job_dir(job_id)

    slug = meta["slug"]



    if kind == "md":

        if meta.get("md_with_images"):

            path = job_dir / "export.bundle"

            name = f"{slug}_yearbook_markdown.zip"

            mime = "application/zip"

        else:

            path = job_dir / "yearbook.md"

            name = f"{slug}_yearbook.md"

            mime = "text/markdown"

    elif kind == "pdf":

        path, name, mime = job_dir / "yearbook.pdf", f"{slug}_yearbook.pdf", "application/pdf"

    else:

        abort(404)



    if not path.is_file():

        abort(404)

    return send_file(path, as_attachment=True, download_name=name, mimetype=mime)





if __name__ == "__main__":

    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    port = int(os.environ.get("PORT", "5000"))

    app.run(host="0.0.0.0", port=port, debug=debug) 