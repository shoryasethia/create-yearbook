"""Standalone IITB Yearbook scraper and exporter.

Does NOT use fetch-my-memories — only talks to the public Yearbook API.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

PDF_ACCENT = colors.HexColor("#5B2C8E")
PDF_MUTED = colors.HexColor("#6B7280")
PDF_LINE = colors.HexColor("#E4E4E7")
PDF_BODY = colors.HexColor("#27272A")

BASE_URL = "https://yearbook.sarc-iitb.org"


@dataclass
class YearbookData:
    profile_id: int
    name: str
    posts_for: list[dict[str, Any]]
    posts_by: list[dict[str, Any]]
    gallery: dict[str, Any] | None
    gallery_images: list[tuple[str, bytes]]


class YearbookClient:
    def __init__(self, username: str, password: str):
        self.username = self._normalize_username(username)
        self.password = password
        self._headers: dict[str, str] = {}
        self._login()

    @staticmethod
    def _normalize_username(username: str) -> str:
        username = username.strip()
        if "@" not in username:
            return f"{username}@iitb.ac.in"
        return username

    def _login(self) -> None:
        response = requests.post(
            f"{BASE_URL}/api/authenticate/token/",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        if response.status_code != 200:
            raise ValueError("Invalid credentials. Check username and password.")
        token = response.json()["access"]
        self._headers = {"Authorization": f"Bearer {token}"}

    def _get_json(self, path: str) -> Any:
        response = requests.get(f"{BASE_URL}{path}", headers=self._headers, timeout=60)
        if response.status_code != 200:
            return None
        return response.json()

    def current_user_id(self) -> int:
        data = self._get_json("/api/authenticate/current_user/")
        if not data:
            raise ValueError("Could not load current user.")
        return int(data["id"])

    def fetch(self, profile_id: int | None = None, include_gallery: bool = True) -> YearbookData:
        pid = profile_id or self.current_user_id()
        posts_for = self._get_json(f"/api/posts/others/{pid}") or []
        posts_by = self._get_json(f"/api/posts/my/{pid}") or []
        gallery = self._get_json(f"/api/authenticate/profile/{pid}/gallery/") if include_gallery else None

        name = self._resolve_name(pid, posts_for, posts_by, gallery)
        gallery_images: list[tuple[str, bytes]] = []
        if gallery:
            gallery_images = self._download_gallery(gallery)

        return YearbookData(
            profile_id=pid,
            name=name,
            posts_for=posts_for,
            posts_by=posts_by,
            gallery=gallery,
            gallery_images=gallery_images,
        )

    def _resolve_name(
        self,
        profile_id: int,
        posts_for: list,
        posts_by: list,
        gallery: dict | None,
    ) -> str:
        profile = self._get_json(f"/api/authenticate/profile/{profile_id}/")
        if isinstance(profile, dict) and profile.get("name"):
            return profile["name"]
        sample = (posts_for or posts_by or [None])[0]
        if sample:
            return sample.get("written_for") or sample.get("written_by") or f"Profile {profile_id}"
        return f"Profile {profile_id}"

    def _download_gallery(self, gallery: dict) -> list[tuple[str, bytes]]:
        images: list[tuple[str, bytes]] = []
        keys = ["cover"] + [k for k in gallery if k.startswith("img")]
        for key in keys:
            path = gallery.get(key)
            if not path:
                continue
            url = path if path.startswith("http") else f"{BASE_URL}{path}"
            try:
                response = requests.get(url, headers=self._headers, timeout=60)
                if response.status_code == 200 and len(response.content) > 500:
                    if not _is_dark_placeholder(response.content):
                        images.append((key, response.content))
            except requests.RequestException:
                continue
        return images


def export_json(data: YearbookData) -> str:
    payload = {
        "profile": {"id": data.profile_id, "name": data.name},
        "posts_written_for": data.posts_for,
        "posts_written_by": data.posts_by,
        "gallery": data.gallery,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def export_markdown(data: YearbookData) -> str:
    lines = [f"# Yearbook — {data.name}", "", f"Profile ID: {data.profile_id}", ""]

    if data.gallery_images:
        lines.extend(["## Gallery", ""])
        for key, raw in data.gallery_images:
            _, ext = _optimize_image(raw)
            lines.append(f"![](gallery/{key}{ext})")
        lines.append("")

    lines.extend([f"## Posts written for {data.name} ({len(data.posts_for)})", ""])
    for i, post in enumerate(data.posts_for, 1):
        lines.extend(_format_post_md(i, post, direction="for", subject=data.name))

    lines.extend([f"## Posts written by {data.name} ({len(data.posts_by)})", ""])
    for i, post in enumerate(data.posts_by, 1):
        lines.extend(_format_post_md(i, post, direction="by", subject=data.name))

    return "\n".join(lines)


def _format_post_md(i: int, post: dict, direction: str, subject: str) -> list[str]:
    if direction == "for":
        author, recipient = post.get("written_by", "Unknown"), post.get("written_for", subject)
        dept, year = post.get("written_by_dept"), post.get("written_by_year")
    else:
        author, recipient = post.get("written_by", subject), post.get("written_for", "Unknown")
        dept, year = post.get("written_for_dept"), post.get("written_for_year")

    lines = [f"### {i}. {author} → {recipient}"]
    if dept and dept != "None":
        lines.append(f"*{dept}* · {year or ''}")
    lines.extend(["", post.get("content", "").strip(), "", "---", ""])
    return lines


def _safe_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"[^\x00-\u024F\u1E00-\u1EFF\s\.,!?;:'\"()\-@#&/\\]", "", text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pdf_page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(PDF_MUTED)
    canvas.drawCentredString(letter[0] / 2, 0.45 * inch, f"Yearbook - {doc.title.split(' - ', 1)[-1]}  |  {canvas.getPageNumber()}")
    canvas.restoreState()


def export_pdf(data: YearbookData, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "YBTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=30,
        textColor=PDF_ACCENT,
        alignment=TA_CENTER,
        leading=34,
        spaceAfter=6,
    )
    cover_subtitle_style = ParagraphStyle(
        "YBCoverSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=PDF_MUTED,
        alignment=TA_CENTER,
        leading=14,
        spaceBefore=10,
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "YBSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=17,
        textColor=PDF_ACCENT,
        alignment=TA_CENTER,
        spaceBefore=8,
        spaceAfter=18,
    )
    meta_style = ParagraphStyle(
        "YBMeta",
        parent=styles["Normal"],
        fontSize=9,
        textColor=PDF_MUTED,
        spaceAfter=4,
        leading=12,
    )
    body_style = ParagraphStyle(
        "YBBody",
        parent=styles["Normal"],
        fontSize=11,
        leading=16,
        textColor=PDF_BODY,
        spaceAfter=4,
    )
    author_style = ParagraphStyle(
        "YBAuthor",
        parent=styles["Normal"],
        fontSize=12,
        textColor=PDF_ACCENT,
        spaceAfter=3,
        fontName="Helvetica-Bold",
        leading=15,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=60,
        leftMargin=60,
        topMargin=60,
        bottomMargin=60,
        title=f"Yearbook - {data.name}",
    )
    story: list = []

    story.append(Spacer(1, 2.1 * inch))
    story.append(Paragraph(_safe_text(f"Yearbook"), title_style))
    story.append(Paragraph(_safe_text(data.name), title_style))
    story.append(Spacer(1, 0.12 * inch))
    story.append(HRFlowable(width="36%", thickness=1.2, color=PDF_ACCENT, spaceBefore=4, spaceAfter=4, hAlign="CENTER"))
    story.append(Paragraph(_safe_text("IIT Bombay - SARC Yearbook 2026"), cover_subtitle_style))
    story.append(PageBreak())

    if data.gallery_images:
        story.append(Paragraph("Gallery", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=PDF_LINE, spaceAfter=16))
        for _key, raw in data.gallery_images:
            try:
                img = RLImage(BytesIO(raw))
                max_w, max_h = 5.2 * inch, 4 * inch
                ratio = min(max_w / img.drawWidth, max_h / img.drawHeight)
                img.drawWidth = img.drawWidth * ratio
                img.drawHeight = img.drawHeight * ratio
                img.hAlign = "CENTER"
                story.append(KeepTogether([img, Spacer(1, 0.3 * inch)]))
            except Exception:
                continue
        story.append(PageBreak())

    story.append(Paragraph(_safe_text(f"Posts written for {data.name}"), section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=PDF_LINE, spaceAfter=14))
    for i, post in enumerate(data.posts_for):
        story.extend(_pdf_post_blocks(post, "for", data.name, author_style, meta_style, body_style, first=i == 0))

    story.append(PageBreak())
    story.append(Paragraph(_safe_text(f"Posts written by {data.name}"), section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=PDF_LINE, spaceAfter=14))
    for i, post in enumerate(data.posts_by):
        story.extend(_pdf_post_blocks(post, "by", data.name, author_style, meta_style, body_style, first=i == 0))

    doc.build(story, onFirstPage=_pdf_page_footer, onLaterPages=_pdf_page_footer)
    return output_path


def _pdf_post_blocks(post, direction, subject, author_style, meta_style, body_style, *, first: bool = False):
    if direction == "for":
        header = f"{post.get('written_by', 'Unknown')} -> {post.get('written_for', subject)}"
        dept, year = post.get("written_by_dept"), post.get("written_by_year")
    else:
        header = f"{post.get('written_by', subject)} -> {post.get('written_for', 'Unknown')}"
        dept, year = post.get("written_for_dept"), post.get("written_for_year")

    blocks: list = []
    if not first:
        blocks.append(Spacer(1, 0.08 * inch))
        blocks.append(HRFlowable(width="100%", thickness=0.5, color=PDF_LINE, spaceBefore=2, spaceAfter=10))
    blocks.append(Paragraph(_safe_text(header), author_style))
    if dept and dept != "None":
        blocks.append(Paragraph(_safe_text(f"{dept} - {year or ''}"), meta_style))
    content = _safe_text(post.get("content", "").strip()).replace("\n", "<br/>")
    blocks.append(Paragraph(content or "(empty)", body_style))
    blocks.append(Spacer(1, 0.12 * inch))
    return blocks


def _image_ext(raw: bytes) -> str:
    return ".png" if raw[:4] == b"\x89PNG" else ".jpg"


def _is_dark_placeholder(raw: bytes) -> bool:
    """Skip empty gallery slots that return solid black placeholder images."""
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return False

    try:
        img = Image.open(BytesIO(raw)).convert("RGB")
        mean_brightness = sum(ImageStat.Stat(img).mean) / 3
        if mean_brightness < 18:
            return True

        sample = img.resize((64, 64), Image.Resampling.NEAREST)
        pixels = sample.getdata()
        dark = sum(1 for r, g, b in pixels if (r + g + b) / 3 < 28)
        return dark / len(pixels) > 0.9
    except Exception:
        return False


def _optimize_image(raw: bytes, max_edge: int = 1600, jpeg_quality: int = 82) -> tuple[bytes, str]:
    """Resize large gallery images to keep exports lightweight. Returns (bytes, ext)."""
    try:
        from PIL import Image
    except ImportError:
        return raw, _image_ext(raw)

    try:
        img = Image.open(BytesIO(raw))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            ext = ".jpg"
        else:
            ext = _image_ext(raw)

        w, h = img.size
        if max(w, h) > max_edge:
            scale = max_edge / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

        out = BytesIO()
        if ext == ".png":
            img.save(out, format="PNG", optimize=True)
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(out, format="JPEG", quality=jpeg_quality, optimize=True)
            ext = ".jpg"
        return out.getvalue(), ext
    except Exception:
        return raw, _image_ext(raw)


def build_markdown_bundle(data: YearbookData, markdown: str) -> bytes:
    """Markdown + JSON + optimized gallery images (single download, no PDF)."""
    import zipfile

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("yearbook.md", markdown)
        zf.writestr("yearbook.json", export_json(data))
        for key, raw in data.gallery_images:
            optimized, ext = _optimize_image(raw)
            zf.writestr(f"gallery/{key}{ext}", optimized)
    buffer.seek(0)
    return buffer.read()


def build_zip_with_images(data: YearbookData, markdown: str) -> bytes:
    return build_markdown_bundle(data, markdown)


def build_full_archive(
    data: YearbookData,
    markdown: str,
    pdf_path: str | Path | None = None,
) -> bytes:
    """Zip with PDF, Markdown, JSON, and gallery images."""
    import zipfile

    buffer = BytesIO()
    pdf_path = Path(pdf_path) if pdf_path else None
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("yearbook.md", markdown)
        zf.writestr("yearbook.json", export_json(data))
        if pdf_path and pdf_path.is_file():
            zf.write(pdf_path, "yearbook.pdf")
        for key, raw in data.gallery_images:
            zf.writestr(f"gallery/{key}{_image_ext(raw)}", raw)
    buffer.seek(0)
    return buffer.read()


def cli_main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Scrape IITB Yearbook posts and gallery.")
    parser.add_argument("--username", default=os.environ.get("YB_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("YB_PASSWORD", ""))
    parser.add_argument("--profile-id", type=int, default=None)
    parser.add_argument("--format", choices=["md", "pdf", "both"], default="both")
    parser.add_argument("--no-gallery", action="store_true")
    args = parser.parse_args()

    if not args.username or not args.password:
        raise SystemExit("Set --username/--password or YB_USERNAME/YB_PASSWORD.")

    client = YearbookClient(args.username, args.password)
    data = client.fetch(profile_id=args.profile_id, include_gallery=not args.no_gallery)
    slug = re.sub(r"[^\w\-]+", "_", data.name.lower()).strip("_") or "yearbook"

    if args.format in ("md", "both"):
        Path(f"{slug}_posts.md").write_text(export_markdown(data), encoding="utf-8")
        print(f"Wrote {slug}_posts.md")
    if args.format in ("pdf", "both"):
        export_pdf(data, f"{slug}_yearbook.pdf")
        print(f"Wrote {slug}_yearbook.pdf")

    print(f"{data.name}: {len(data.posts_for)} for, {len(data.posts_by)} by, {len(data.gallery_images)} images")


if __name__ == "__main__":
    cli_main()
