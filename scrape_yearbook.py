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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PDF_ACCENT = colors.HexColor("#5B2C8E")
PDF_MUTED = colors.HexColor("#6B7280")
PDF_LINE = colors.HexColor("#E4E4E7")
PDF_BODY = colors.HexColor("#27272A")

BASE_URL = "https://yearbook.sarc-iitb.org"
FONT_DIR = Path(__file__).resolve().parent / "static" / "fonts"
_EMOJI_RE = re.compile(
    r"(?:"
    r"[\U0001F1E6-\U0001F1FF]{2}"
    r"|[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F600-\U0001F64F"
    r"\U0001F680-\U0001F6FF\U00002600-\U000026FF\U0000231A-\U0000231B"
    r"\U000023E9-\U000023F3\U000023F8-\U000023FA\U000025AA-\U000025AB"
    r"\U000025B6\U000025C0\U000025FB-\U000025FE\U00002614-\U00002615"
    r"\U00002648-\U00002653\U0000267F\U00002693\U000026A1\U000026AA-\U000026AB"
    r"\U000026BD-\U000026BE\U000026C4-\U000026C5\U000026CE\U000026D4"
    r"\U000026EA\U000026F2-\U000026F3\U000026F5\U000026FA\U000026FD"
    r"\U00002705\U0000270A-\U0000270B\U00002728\U0000274C\U0000274E"
    r"\U00002753-\U00002755\U00002757\U00002795-\U00002797\U000027B0"
    r"\U000027BF\U00002B1B-\U00002B1C\U00002B50\U00002B55]"
    r"[\U0000FE0E\U0000FE0F\U0000200D\U0001F3FB-\U0001F3FF]*"
    r")+"
)
_PDF_FONTS_READY = False
_EMOJI_CACHE_DIR: Path | None = None
_TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"


@dataclass
class YearbookData:
    profile_id: int
    name: str
    profile: dict[str, Any] | None
    profile_photo: bytes | None
    profile_images: dict[str, bytes]
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
            raise ValueError(
                f"Login failed (HTTP {response.status_code}): {response.text[:200]}"
            )
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
        profile = self._get_json(f"/api/authenticate/profile/{pid}/")

        name = _profile_name(profile, pid, posts_for, posts_by)
        profile_dict = profile if isinstance(profile, dict) else None
        profile_photo_path = _subject_profile_image_path(profile_dict, posts_for, posts_by)
        profile_images = self._download_post_profile_images(posts_for, posts_by, profile_photo_path)
        profile_photo = None
        if profile_photo_path and profile_photo_path in profile_images:
            profile_photo = profile_images[profile_photo_path]
        elif profile_photo_path:
            profile_photo = self._download_image(profile_photo_path, min_size=50, check_placeholder=False)

        gallery_images: list[tuple[str, bytes]] = []
        if gallery:
            gallery_images = self._download_gallery(gallery)

        return YearbookData(
            profile_id=pid,
            name=name,
            profile=profile_dict,
            profile_photo=profile_photo,
            profile_images=profile_images,
            posts_for=posts_for,
            posts_by=posts_by,
            gallery=gallery,
            gallery_images=gallery_images,
        )

    def _download_image(
        self,
        path: str | None,
        *,
        min_size: int = 200,
        check_placeholder: bool = True,
    ) -> bytes | None:
        if not path:
            return None
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        try:
            response = requests.get(url, headers=self._headers, timeout=60)
            if response.status_code != 200 or len(response.content) < min_size:
                return None
            if check_placeholder and _is_dark_placeholder(response.content):
                return None
            return response.content
        except requests.RequestException:
            return None

    def _download_post_profile_images(
        self,
        posts_for: list,
        posts_by: list,
        main_path: str | None,
    ) -> dict[str, bytes]:
        paths: set[str] = set()
        if main_path:
            paths.add(main_path)
        for post in posts_for + posts_by:
            for key in ("written_by_profile", "written_for_profile"):
                path = _profile_image_path(post.get(key) or {})
                if path:
                    paths.add(path)

        images: dict[str, bytes] = {}
        for path in paths:
            raw = self._download_image(path, min_size=100, check_placeholder=False)
            if raw:
                images[path] = raw
        return images

    def _download_gallery(self, gallery: dict) -> list[tuple[str, bytes]]:
        images: list[tuple[str, bytes]] = []
        keys = ["cover"] + [k for k in gallery if k.startswith("img")]
        for key in keys:
            raw = self._download_image(gallery.get(key), min_size=500)
            if raw:
                images.append((key, raw))
        return images


def _profile_image_path(profile: dict[str, Any] | None) -> str | None:
    if not profile:
        return None
    for key in ("profile_image", "profile_pic", "photo", "image", "avatar", "picture"):
        path = profile.get(key)
        if path:
            return str(path)
    user = profile.get("user")
    if isinstance(user, dict):
        return _profile_image_path(user)
    return None


def _subject_profile_image_path(
    profile: dict[str, Any] | None,
    posts_for: list,
    posts_by: list,
) -> str | None:
    """Resolve the yearbook subject's profile photo URL from profile API or posts."""
    path = _profile_image_path(profile)
    if path:
        return path
    for post in posts_for:
        path = _profile_image_path(post.get("written_for_profile"))
        if path:
            return path
    for post in posts_by:
        path = _profile_image_path(post.get("written_by_profile"))
        if path:
            return path
    return None


def _profile_name(
    profile: dict[str, Any] | None,
    profile_id: int,
    posts_for: list,
    posts_by: list,
) -> str:
    if isinstance(profile, dict) and profile.get("name"):
        return profile["name"]
    sample = (posts_for or posts_by or [None])[0]
    if sample:
        return sample.get("written_for") or sample.get("written_by") or f"Profile {profile_id}"
    return f"Profile {profile_id}"


def export_json(data: YearbookData) -> str:
    profile_payload: dict[str, Any] = {"id": data.profile_id, "name": data.name}
    if data.profile:
        profile_payload.update(data.profile)
    payload = {
        "profile": profile_payload,
        "has_profile_photo": bool(data.profile_photo),
        "posts_written_for": data.posts_for,
        "posts_written_by": data.posts_by,
        "gallery": data.gallery,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def export_markdown(data: YearbookData) -> str:
    lines = [f"# Yearbook — {data.name}", ""]
    if data.profile_photo:
        _, ext = _optimize_image(data.profile_photo, max_edge=800)
        lines.append(f"![Profile photo](profile{ext})")
        lines.append("")
    lines.extend([f"Profile ID: {data.profile_id}", ""])

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


def _register_pdf_fonts() -> None:
    global _PDF_FONTS_READY
    if _PDF_FONTS_READY:
        return

    font_files = {
        "NotoSans": "NotoSans-Regular.ttf",
        "NotoSans-Bold": "NotoSans-Bold.ttf",
    }
    for name, filename in font_files.items():
        path = FONT_DIR / filename
        if path.is_file():
            pdfmetrics.registerFont(TTFont(name, str(path)))

    _PDF_FONTS_READY = True


def _escape_xml(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pdf_body_font() -> str:
    return "NotoSans" if "NotoSans" in pdfmetrics.getRegisteredFontNames() else "Helvetica"


def _pdf_bold_font() -> str:
    return "NotoSans-Bold" if "NotoSans-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"


def _set_emoji_cache_dir(path: Path | None) -> None:
    global _EMOJI_CACHE_DIR
    _EMOJI_CACHE_DIR = path


def _twemoji_codepoints(emoji: str) -> list[str]:
    return [f"{ord(char):x}" for char in emoji]


def _twemoji_png(emoji: str) -> bytes | None:
    codepoints = _twemoji_codepoints(emoji)
    candidates = [codepoints]
    if codepoints and codepoints[-1] == "fe0f":
        candidates.append(codepoints[:-1])

    for parts in candidates:
        slug = "-".join(parts)
        url = f"{_TWEMOJI_BASE}/{slug}.png"
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200 and response.content:
                return response.content
        except requests.RequestException:
            continue
    return None


def _emoji_img_markup(emoji: str, *, size: int = 13) -> str:
    if not _EMOJI_CACHE_DIR:
        return _escape_xml(emoji)

    slug = "-".join(_twemoji_codepoints(emoji))
    img_path = _EMOJI_CACHE_DIR / f"{slug}.png"
    if not img_path.is_file():
        raw = _twemoji_png(emoji)
        if not raw:
            return _escape_xml(emoji)
        img_path.write_bytes(raw)

    src = img_path.resolve().as_posix()
    return f'<img src="{src}" width="{size}" height="{size}" valign="middle"/>'


def _paragraph_markup(text: str, *, font: str | None = None, emoji_size: int = 13) -> str:
    text = _escape_xml(text)
    body_font = font or _pdf_body_font()
    if not _EMOJI_RE.search(text):
        return f'<font face="{body_font}">{text}</font>'

    parts: list[str] = []
    pos = 0
    for match in _EMOJI_RE.finditer(text):
        if match.start() > pos:
            parts.append(f'<font face="{body_font}">{text[pos:match.start()]}</font>')
        parts.append(_emoji_img_markup(match.group(), size=emoji_size))
        pos = match.end()
    if pos < len(text):
        parts.append(f'<font face="{body_font}">{text[pos:]}</font>')
    return "".join(parts) or f'<font face="{body_font}"></font>'


def _pdf_page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(PDF_MUTED)
    canvas.drawCentredString(letter[0] / 2, 0.45 * inch, f"Yearbook - {doc.title.split(' - ', 1)[-1]}  |  {canvas.getPageNumber()}")
    canvas.restoreState()


def export_pdf(data: YearbookData, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    emoji_cache = output_path.parent / f".emoji_{output_path.stem}"
    emoji_cache.mkdir(parents=True, exist_ok=True)
    _set_emoji_cache_dir(emoji_cache)
    _register_pdf_fonts()
    body_font = _pdf_body_font()
    bold_font = _pdf_bold_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "YBTitle",
        parent=styles["Heading1"],
        fontName=bold_font,
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
        fontName=bold_font,
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
        fontName=body_font,
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
        fontName=bold_font,
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

    if data.profile_photo:
        try:
            photo = _pdf_scaled_image(data.profile_photo, max_size=2.4 * inch)
            story.append(Spacer(1, 1.1 * inch))
            story.append(photo)
            story.append(Spacer(1, 0.22 * inch))
        except Exception:
            story.append(Spacer(1, 2.0 * inch))
    else:
        story.append(Spacer(1, 2.0 * inch))
    story.append(Paragraph(_paragraph_markup(data.name, font=bold_font), title_style))
    story.append(Spacer(1, 0.08 * inch))
    story.append(Paragraph(_paragraph_markup("Yearbook", font=bold_font), title_style))
    story.append(Spacer(1, 0.12 * inch))
    story.append(HRFlowable(width="36%", thickness=1.2, color=PDF_ACCENT, spaceBefore=4, spaceAfter=4, hAlign="CENTER"))
    story.append(Paragraph(_paragraph_markup("IIT Bombay - SARC Yearbook 2026"), cover_subtitle_style))
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

    story.append(Paragraph(_paragraph_markup(f"Posts written for {data.name}", font=bold_font), section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=PDF_LINE, spaceAfter=14))
    for i, post in enumerate(data.posts_for):
        story.extend(
            _pdf_post_blocks(
                post, "for", data.name, author_style, meta_style, body_style,
                profile_images=data.profile_images, first=i == 0,
            )
        )

    story.append(PageBreak())
    story.append(Paragraph(_paragraph_markup(f"Posts written by {data.name}", font=bold_font), section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=PDF_LINE, spaceAfter=14))
    for i, post in enumerate(data.posts_by):
        story.extend(
            _pdf_post_blocks(
                post, "by", data.name, author_style, meta_style, body_style,
                profile_images=data.profile_images, first=i == 0,
            )
        )

    try:
        doc.build(story, onFirstPage=_pdf_page_footer, onLaterPages=_pdf_page_footer)
    finally:
        _set_emoji_cache_dir(None)
    return output_path


def _pdf_scaled_image(raw: bytes, max_size: float) -> RLImage:
    from PIL import Image

    with Image.open(BytesIO(raw)) as pil:
        width_px, height_px = pil.size
    if width_px <= 0 or height_px <= 0:
        raise ValueError("invalid image dimensions")

    scale = min(max_size / width_px, max_size / height_px)
    draw_w = width_px * scale
    draw_h = height_px * scale
    img = RLImage(BytesIO(raw), width=draw_w, height=draw_h)
    img.hAlign = "CENTER"
    return img


def _pdf_post_avatar(raw: bytes | None, size: float = 0.5 * inch) -> RLImage | Spacer:
    if not raw:
        return Spacer(size, size)
    try:
        return _pdf_scaled_image(raw, size)
    except Exception:
        return Spacer(size, size)


def _pdf_post_blocks(
    post,
    direction,
    subject,
    author_style,
    meta_style,
    body_style,
    *,
    profile_images: dict[str, bytes],
    first: bool = False,
):
    if direction == "for":
        header = f"{post.get('written_by', 'Unknown')} -> {post.get('written_for', subject)}"
        dept, year = post.get("written_by_dept"), post.get("written_by_year")
        by_path = _profile_image_path(post.get("written_by_profile") or {})
        for_path = _profile_image_path(post.get("written_for_profile") or {})
    else:
        header = f"{post.get('written_by', subject)} -> {post.get('written_for', 'Unknown')}"
        dept, year = post.get("written_for_dept"), post.get("written_for_year")
        by_path = _profile_image_path(post.get("written_by_profile") or {})
        for_path = _profile_image_path(post.get("written_for_profile") or {})

    blocks: list = []
    if not first:
        blocks.append(Spacer(1, 0.08 * inch))
        blocks.append(HRFlowable(width="100%", thickness=0.5, color=PDF_LINE, spaceBefore=2, spaceAfter=10))

    avatar_size = 0.5 * inch
    header_para = Paragraph(_paragraph_markup(header, font=_pdf_bold_font()), author_style)
    header_row = Table(
        [
            [
                _pdf_post_avatar(profile_images.get(by_path) if by_path else None, avatar_size),
                header_para,
                _pdf_post_avatar(profile_images.get(for_path) if for_path else None, avatar_size),
            ]
        ],
        colWidths=[0.65 * inch, 4.9 * inch, 0.65 * inch],
    )
    header_row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    blocks.append(header_row)
    if dept and dept != "None":
        blocks.append(Paragraph(_paragraph_markup(f"{dept} - {year or ''}"), meta_style))
    content = _paragraph_markup(post.get("content", "").strip()).replace("\n", "<br/>")
    blocks.append(Paragraph(content or _paragraph_markup("(empty)"), body_style))
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
        if data.profile_photo:
            optimized, ext = _optimize_image(data.profile_photo, max_edge=800)
            zf.writestr(f"profile{ext}", optimized)
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
        if data.profile_photo:
            optimized, ext = _optimize_image(data.profile_photo, max_edge=800)
            zf.writestr(f"profile{ext}", optimized)
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
