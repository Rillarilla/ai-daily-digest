"""
Email sender module with PDF attachment support.
"""

import os
import smtplib
import sys
import ctypes.util
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from collectors.base import NewsItem


def _configure_weasyprint_macos_libs():
    """Help WeasyPrint find Homebrew GTK libs on macOS."""
    if sys.platform != "darwin":
        return

    prefix = "/opt/homebrew/lib"
    library_map = {
        "gobject-2.0-0": f"{prefix}/libgobject-2.0-0.dylib",
        "libgobject-2.0-0": f"{prefix}/libgobject-2.0-0.dylib",
        "pango-1.0-0": f"{prefix}/libpango-1.0-0.dylib",
        "libpango-1.0-0": f"{prefix}/libpango-1.0-0.dylib",
        "harfbuzz-0": f"{prefix}/libharfbuzz-0.dylib",
        "libharfbuzz-0": f"{prefix}/libharfbuzz-0.dylib",
        "harfbuzz-subset-0": f"{prefix}/libharfbuzz-subset.0.dylib",
        "libharfbuzz-subset-0": f"{prefix}/libharfbuzz-subset.0.dylib",
        "fontconfig-1": f"{prefix}/libfontconfig-1.dylib",
        "libfontconfig-1": f"{prefix}/libfontconfig-1.dylib",
        "pangoft2-1.0-0": f"{prefix}/libpangoft2-1.0-0.dylib",
        "libpangoft2-1.0-0": f"{prefix}/libpangoft2-1.0-0.dylib",
    }

    if not all(Path(path).exists() for path in library_map.values()):
        return

    original_find_library = ctypes.util.find_library

    def _patched_find_library(name: str):
        return library_map.get(name) or original_find_library(name)

    ctypes.util.find_library = _patched_find_library


# Try to import weasyprint for PDF generation
try:
    _configure_weasyprint_macos_libs()
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False
    print("[PDF] weasyprint not installed, PDF generation disabled")
    print("[PDF] Install with: pip install weasyprint")


def _compress_html_images(html_content: str, max_side: int = 400, quality: int = 70, timeout: int = 10) -> str:
    """Download and shrink remote <img> sources, inlining them as JPEG data URIs.

    News images embedded at full resolution can push the rendered PDF past
    Feishu's 20MB upload limit. Compressing each image to a small thumbnail
    keeps the PDF comfortably under the limit while preserving the layout.

    On any per-image failure the image is replaced with a 1x1 transparent
    pixel so WeasyPrint never fetches the full-size remote file (which would
    defeat the size reduction).
    """
    import re
    import io
    import base64

    try:
        import requests
        from PIL import Image
    except ImportError as e:
        print(f"[PDF] Image compression unavailable ({e}), keeping original images")
        return html_content

    TRANSPARENT_PX = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
    cache: dict[str, str] = {}
    stats = {"count": 0, "orig": 0, "new": 0}

    def compress_one(url: str) -> str:
        if url in cache:
            return cache[url]
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            orig_len = len(resp.content)
            img = Image.open(io.BytesIO(resp.content))
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((max_side, max_side), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            stats["count"] += 1
            stats["orig"] += orig_len
            stats["new"] += len(data)
            result = "data:image/jpeg;base64," + base64.b64encode(data).decode()
        except Exception as e:
            print(f"[PDF] Image compress skip ({url[:60]}): {e}")
            result = TRANSPARENT_PX
        cache[url] = result
        return result

    def replace_img(match: "re.Match") -> str:
        tag = match.group(0)
        m = re.search(r'src=["\']([^"\']+)["\']', tag)
        if not m:
            return tag
        url = m.group(1)
        if not url.startswith("http"):
            return tag  # already inlined or local
        new_src = compress_one(url)
        return tag[:m.start(1)] + new_src + tag[m.end(1):]

    result = re.sub(r"<img\b[^>]*>", replace_img, html_content, flags=re.IGNORECASE)
    if stats["count"]:
        print(f"[PDF] Compressed {stats['count']} images: "
              f"{stats['orig']/1024/1024:.1f}MB → {stats['new']/1024/1024:.2f}MB")
    return result


class EmailSender:
    """Send HTML emails via SMTP with optional PDF attachment."""

    def __init__(
        self,
        smtp_server: str = None,
        smtp_port: int = None,
        smtp_user: str = None,
        smtp_password: str = None,
        from_email: str = None,
    ):
        self.smtp_server = smtp_server or os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.environ.get("SMTP_USER")
        self.smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD")
        self.from_email = from_email or os.environ.get("FROM_EMAIL", self.smtp_user)

        # Setup Jinja2 template environment
        template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))

    def render_email(
        self,
        categories: dict[str, list[NewsItem]],
        category_names: dict[str, str],
        highlights: str = "",
    ) -> str:
        """Render email HTML from template."""
        template = self.jinja_env.get_template("email.html")

        # Count total items
        item_count = sum(len(items) for items in categories.values())

        # Render
        html = template.render(
            date=datetime.now().strftime("%Y年%m月%d日"),
            item_count=item_count,
            highlights=highlights,
            categories=categories,
            category_names=category_names,
        )

        return html

    def generate_pdf(self, html_content: str, output_path: str) -> bool:
        """Generate PDF from HTML content."""
        if not WEASYPRINT_AVAILABLE:
            print("[PDF] weasyprint not available, skipping PDF generation")
            return False

        try:
            # PDF-specific CSS adjustments
            # 添加中文字体支持并优化排版（减少空白）
            pdf_css = CSS(string='''
                @page {
                    size: A4;
                    margin: 1cm; /* 减小页边距 */
                }
                body {
                    font-size: 10.5px; /* 稍微减小字号 */
                    line-height: 1.5; /* 减小行高 */
                    font-family: "PingFang SC", "Heiti SC", "Microsoft YaHei", "WenQuanYi Micro Hei", "Noto Sans SC", "Noto Sans CJK SC", "Droid Sans Fallback", "SimSun", sans-serif !important;
                    background-color: #fff;
                }
                .container {
                    max-width: 100% !important;
                    width: 100% !important;
                    margin: 0 !important;
                    box-shadow: none !important;
                }
                .header {
                    padding: 15px 20px !important; /* 减小 Header 内边距 */
                }
                .header h1 {
                    font-size: 24px !important;
                    margin-bottom: 4px !important;
                }
                .highlights {
                    padding: 15px 20px !important; /* 减小 Highlights 内边距 */
                }
                .highlight-item {
                    padding: 10px 15px !important;
                    margin-bottom: 10px !important;
                }
                .category {
                    padding: 15px 20px !important; /* 减小分类内边距 */
                    border-bottom: 1px solid #eee !important;
                }
                .category-header {
                    margin-bottom: 12px !important;
                    font-size: 16px !important;
                    padding-bottom: 8px !important;
                }
                .news-item {
                    padding: 12px !important; /* 减小新闻卡片内边距 */
                    margin-bottom: 12px !important; /* 减小卡片间距 */
                    border: 1px solid #eee !important;
                    box-shadow: none !important;
                    page-break-inside: avoid;
                }
                .news-title {
                    font-size: 14px !important;
                    margin-bottom: 6px !important;
                }
                .news-meta {
                    margin-bottom: 8px !important;
                    font-size: 12px !important;
                }
                .news-summary {
                    font-size: 13px !important;
                    margin-top: 8px !important;
                    line-height: 1.5 !important;
                }
                /* Image is first in DOM; float:right so text wraps to the left */
                .news-content-wrapper {
                    display: block !important;
                    overflow: hidden !important;
                }
                .news-image {
                    float: right !important;
                    width: 80px !important;
                    height: 60px !important;
                    margin-left: 12px !important;
                    border-radius: 6px !important;
                    object-fit: cover !important;
                }
                .news-text {
                    display: block !important;
                }
                /* Table of Contents - allow page breaks inside TOC */
                .toc {
                    padding: 15px 20px !important;
                    /* DO NOT use page-break-inside: avoid on TOC
                       — it's too large and causes blank pages */
                }
                .toc h2 {
                    font-size: 14px !important;
                    margin-bottom: 10px !important;
                    page-break-after: avoid; /* keep title with content */
                }
                .toc-list {
                    display: block !important; /* override flex for PDF */
                }
                .toc-category {
                    page-break-inside: avoid;
                    margin-bottom: 8px !important;
                }
                .toc-category-title {
                    font-size: 14px !important;
                    margin-bottom: 6px !important;
                    page-break-after: avoid; /* keep with items below */
                }
                .toc-category-title a {
                    color: #1f2937 !important;
                    text-decoration: none !important;
                }
                .toc-item-link {
                    font-size: 13px !important;
                    margin-bottom: 4px !important;
                }
                .toc-item-link a {
                    color: #4338ca !important;
                    text-decoration: none !important;
                }
                .toc-count {
                    font-size: 11px !important;
                }
                /* Highlights — allow page breaks, keep individual items intact */
                .highlights {
                    /* DO NOT use page-break-inside: avoid here either */
                }
                .highlights h2 {
                    font-size: 16px !important;
                    page-break-after: avoid; /* keep title with first item */
                }
                .highlights-content {
                    display: block !important; /* override flex for PDF */
                }
                /* Ensure internal anchor links work */
                a[href^="#"] {
                    color: #4338ca !important;
                }
                /* Hide footer in PDF to save space */
                .footer {
                    padding: 10px !important;
                    font-size: 10px !important;
                }
            ''')

            # Shrink embedded images so the PDF stays under Feishu's 20MB
            # upload limit (otherwise the Feishu doc/button can't be created).
            html_content = _compress_html_images(html_content)

            html = HTML(string=html_content)
            html.write_pdf(output_path, stylesheets=[pdf_css])
            size_mb = Path(output_path).stat().st_size / 1024 / 1024
            print(f"[PDF] Generated: {output_path} ({size_mb:.1f} MB)")
            return True
        except Exception as e:
            print(f"[PDF] Generation error: {e}")
            return False

    def send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        pdf_path: Optional[str] = None,
    ) -> bool:
        """Send email via SMTP with optional PDF attachment."""
        if not self.smtp_user or not self.smtp_password:
            print("SMTP credentials not configured")
            return False

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = to_email

        # Create alternative part for HTML
        alt_part = MIMEMultipart("alternative")

        # Attach HTML content
        html_part = MIMEText(html_content, "html", "utf-8")
        alt_part.attach(html_part)
        msg.attach(alt_part)

        # Attach PDF if provided
        if pdf_path and os.path.exists(pdf_path):
            try:
                with open(pdf_path, "rb") as f:
                    pdf_part = MIMEBase("application", "pdf")
                    pdf_part.set_payload(f.read())
                    encoders.encode_base64(pdf_part)
                    pdf_filename = os.path.basename(pdf_path)
                    pdf_part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={pdf_filename}"
                    )
                    msg.attach(pdf_part)
                    print(f"[Email] PDF attached: {pdf_filename}")
            except Exception as e:
                print(f"[Email] Failed to attach PDF: {e}")

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())
            print(f"Email sent successfully to {to_email}")
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False


def send_digest_email(
    to_email: str,
    categories: dict[str, list[NewsItem]],
    category_names: dict[str, str],
    highlights: str = "",
) -> bool:
    """Convenience function to send digest email with PDF attachment."""
    sender = EmailSender()
    html = sender.render_email(categories, category_names, highlights)

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"🤖 AI Daily Digest - {datetime.now().strftime('%m/%d')}"

    # Generate PDF
    pdf_path = None
    if WEASYPRINT_AVAILABLE:
        pdf_dir = Path(__file__).parent / "output"
        pdf_dir.mkdir(exist_ok=True)
        pdf_path = str(pdf_dir / f"AI_Daily_Digest_{date_str}.pdf")
        sender.generate_pdf(html, pdf_path)

    return sender.send(to_email, subject, html, pdf_path)
