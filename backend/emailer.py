"""CIVIO transactional email via Emergent-managed Resend."""
import os
import re
import ipaddress
import logging
import base64
import httpx
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

logger = logging.getLogger("civio.email")

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "CIVIO")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan(); scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def send_email(*, to, subject: str, html: str, attachments=None) -> str | None:
    """Internal helper. `html` must come from a server-side template, never request input."""
    if not EMAIL_KEY:
        logger.warning("EMERGENT_EMAIL_KEY missing; skipping email send.")
        return None
    _assert_safe_email(subject, html)
    recipients = to if isinstance(to, list) else [to]
    payload = {"to": recipients, "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    if EMAIL_REPLY_TO:
        payload["contact_email"] = EMAIL_REPLY_TO
    if attachments:
        payload["attachments"] = attachments
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        try:
            code = e.response.json().get("code", "")
        except ValueError:
            code = ""
        if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
            logger.warning(f"Email paused: {code} ({e.response.status_code})")
        else:
            logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return None


def pdf_attachment(filename: str, data: bytes) -> dict:
    return {"filename": filename, "content": base64.b64encode(data).decode("ascii")}


_BASE = ('font-family:Arial,Helvetica,sans-serif;color:#1F2421;')


def otp_email_html(name: str, code: str) -> str:
    return (
        f'<table role="presentation" width="100%" style="background:#f4f6f9;padding:24px">'
        f'<tr><td align="center"><table role="presentation" width="480" style="background:#ffffff;'
        f'border-radius:14px;overflow:hidden;{_BASE}">'
        f'<tr><td style="background:#0D1B3E;padding:20px 28px;color:#fff;font-size:20px;'
        f'font-weight:bold;letter-spacing:1px">CIVIO</td></tr>'
        f'<tr><td style="padding:28px">'
        f'<p style="margin:0 0 10px">Hi {escape(name)},</p>'
        f'<p style="margin:0 0 18px">Use this code to verify your email and activate your CIVIO account.</p>'
        f'<div style="font-size:34px;font-weight:bold;letter-spacing:10px;color:#1E6BFF;'
        f'background:#eef3ff;border-radius:10px;padding:16px;text-align:center">{escape(code)}</div>'
        f'<p style="margin:18px 0 0;font-size:13px;color:#5C6460">This code expires in 10 minutes. '
        f'If you did not create a CIVIO account, you can ignore this email.</p>'
        f'<p style="margin:16px 0 0;font-size:12px;color:#888">Sent by CIVIO. We will never ask you '
        f'to share your password by email.</p>'
        f'</td></tr></table></td></tr></table>'
    )


def invite_email_html(name: str, company: str, inviter: str, role: str, link: str) -> str:
    return (
        f'<table role="presentation" width="100%" style="background:#f4f6f9;padding:24px">'
        f'<tr><td align="center"><table role="presentation" width="520" style="background:#ffffff;'
        f'border-radius:14px;overflow:hidden;{_BASE}">'
        f'<tr><td style="background:#0D1B3E;padding:20px 28px;color:#fff;font-size:20px;'
        f'font-weight:bold;letter-spacing:1px">CIVIO</td></tr>'
        f'<tr><td style="padding:28px">'
        f'<p style="margin:0 0 10px">Hi {escape(name)},</p>'
        f'<p style="margin:0 0 18px">{escape(inviter)} has invited you to join <strong>{escape(company)}</strong> '
        f'on CIVIO as a <strong>{escape(role)}</strong>.</p>'
        f'<p style="margin:0 0 22px"><a href="{escape(link)}" style="display:inline-block;background:#1E6BFF;color:#ffffff;'
        f'text-decoration:none;font-weight:bold;padding:12px 22px;border-radius:999px">Accept invitation</a></p>'
        f'<p style="margin:0;font-size:13px;color:#5C6460">This invitation link expires in 7 days. '
        f'If you were not expecting it, you can ignore this email.</p>'
        f'<p style="margin:16px 0 0;font-size:12px;color:#888">Sent by CIVIO — Your Build, Our Expertise.</p>'
        f'</td></tr></table></td></tr></table>'
    )


def report_email_html(name: str, project_name: str, report_title: str, revision: str) -> str:
    return (
        f'<table role="presentation" width="100%" style="background:#f4f6f9;padding:24px">'
        f'<tr><td align="center"><table role="presentation" width="520" style="background:#ffffff;'
        f'border-radius:14px;overflow:hidden;{_BASE}">'
        f'<tr><td style="background:#0D1B3E;padding:20px 28px;color:#fff;font-size:20px;'
        f'font-weight:bold;letter-spacing:1px">CIVIO</td></tr>'
        f'<tr><td style="padding:28px">'
        f'<p style="margin:0 0 10px">Hi {escape(name)},</p>'
        f'<p style="margin:0 0 16px">A new report has been published for your project '
        f'<strong>{escape(project_name)}</strong>.</p>'
        f'<table role="presentation" width="100%" style="background:#eef3ff;border-radius:10px">'
        f'<tr><td style="padding:16px 18px">'
        f'<div style="font-size:16px;font-weight:bold;color:#0D1B3E">{escape(report_title)}</div>'
        f'<div style="font-size:13px;color:#1E6BFF;margin-top:4px">Revision {escape(revision)}</div>'
        f'</td></tr></table>'
        f'<p style="margin:18px 0 0;font-size:14px">The full PDF is attached to this email. '
        f'You can also view it anytime by signing in to CIVIO.</p>'
        f'<p style="margin:16px 0 0;font-size:12px;color:#888">Sent by CIVIO — Your Build, Our Expertise.</p>'
        f'</td></tr></table></td></tr></table>'
    )
