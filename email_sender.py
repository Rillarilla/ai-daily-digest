"""
Email sender module.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

from collectors.base import NewsItem


class EmailSender:
    """Send HTML emails via SMTP."""

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

    def send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
    ) -> bool:
        """Send email via SMTP."""
        if not self.smtp_user or not self.smtp_password:
            print("SMTP credentials not configured")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = to_email

        # Attach HTML content
        html_part = MIMEText(html_content, "html", "utf-8")
        msg.attach(html_part)

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
    """Convenience function to send digest email."""
    sender = EmailSender()
    html = sender.render_email(categories, category_names, highlights)

    date_str = datetime.now().strftime("%m/%d")
    subject = f"🤖 AI Daily Digest - {date_str}"

    return sender.send(to_email, subject, html)
