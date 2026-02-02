"""
Email sender module with PDF attachment support.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from collectors.base import NewsItem

# Try to import weasyprint for PDF generation
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False
    print("[PDF] weasyprint not installed, PDF generation disabled")
    print("[PDF] Install with: pip install weasyprint")


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
                .news-image {
                    max-width: 80px !important;
                    max-height: 60px !important;
                }
                /* Hide footer in PDF to save space */
                .footer {
                    padding: 10px !important;
                    font-size: 10px !important;
                }
            ''')

            html = HTML(string=html_content)
            html.write_pdf(output_path, stylesheets=[pdf_css])
            print(f"[PDF] Generated: {output_path}")
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
