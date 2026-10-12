"""
Media Reporting System - Gmail Ingestion Service
Connects to Gmail via IMAP SSL, searches for media newsletters (e.g. Best Media Info),
extracts email HTML bodies, and ingests them into the Mailer Intelligence database.
"""
from __future__ import annotations

import email
from email.header import decode_header
import imaplib
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.config import settings
from mailer.service import mailer_service

logger = logging.getLogger("gmail-fetcher")


def _decode_mime_words(raw_header: Optional[str]) -> str:
    """Decodes MIME encoded header strings like '=?utf-8?b?...?='."""
    if not raw_header:
        return ""
    decoded_fragments = []
    for fragment, charset in decode_header(raw_header):
        if isinstance(fragment, bytes):
            try:
                decoded_fragments.append(fragment.decode(charset or "utf-8", errors="replace"))
            except Exception:
                decoded_fragments.append(fragment.decode("latin1", errors="replace"))
        else:
            decoded_fragments.append(str(fragment))
    return "".join(decoded_fragments).strip()


def _extract_html_and_text(msg: email.message.Message) -> Tuple[str, str]:
    """
    Recursively extracts the HTML body and plain text from a MIME email message.
    Returns (html_content, text_content).
    """
    html_parts: List[str] = []
    text_parts: List[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in content_disposition.lower():
                continue

            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if not payload:
                continue

            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("latin1", errors="replace")

            if content_type == "text/html":
                html_parts.append(text)
            elif content_type == "text/plain":
                text_parts.append(text)
    else:
        content_type = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("latin1", errors="replace")

            if content_type == "text/html":
                html_parts.append(text)
            else:
                text_parts.append(text)

    html_content = "\n".join(html_parts)
    text_content = "\n".join(text_parts)
    return html_content, text_content


class GmailMailerFetcher:
    """
    Connects to Gmail via IMAP SSL and imports newsletter digests.
    """

    def __init__(
        self,
        email_address: Optional[str] = None,
        app_password: Optional[str] = None,
        imap_server: Optional[str] = None,
        imap_port: Optional[int] = None,
    ):
        self.email_address = email_address or getattr(settings, "GMAIL_EMAIL", "rajxy101@gmail.com")
        self.app_password = app_password or getattr(settings, "GMAIL_APP_PASSWORD", "")
        self.imap_server = imap_server or getattr(settings, "GMAIL_IMAP_SERVER", "imap.gmail.com")
        self.imap_port = imap_port or getattr(settings, "GMAIL_IMAP_PORT", 993)

    def fetch_and_ingest(
        self,
        search_query: Optional[str] = None,
        max_emails: int = 25,
        mark_as_read: bool = False,
        folder: str = "INBOX",
    ) -> Dict[str, Any]:
        """
        Connects to Gmail, queries matching newsletters, parses HTML, and saves them.
        """
        if not self.email_address or not self.app_password:
            raise ValueError(
                "Gmail credentials not configured. Please set GMAIL_EMAIL and GMAIL_APP_PASSWORD (Google App Password)."
            )

        # Normalize 16-char app password (remove spaces if pasted as 'abcd efgh ijkl mnop')
        clean_password = self.app_password.replace(" ", "").strip()

        logger.info("Connecting to Gmail IMAP (%s:%s) for %s...", self.imap_server, self.imap_port, self.email_address)

        mail = None
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, clean_password)
        except Exception as exc:
            logger.error("Gmail IMAP login failed: %s", exc)
            raise RuntimeError(f"Gmail IMAP authentication failed: {exc}")

        try:
            status, _ = mail.select(folder)
            if status != "OK":
                raise RuntimeError(f"Failed to open Gmail folder '{folder}'")

            # Search criteria
            # Default searches for BestMediaInfo or general newsletters
            query = search_query or '(OR FROM "bestmediainfo" SUBJECT "BestMediaInfo")'
            logger.info("Searching Gmail with query: %s", query)

            status, search_data = mail.search(None, query)
            if status != "OK" or not search_data or not search_data[0]:
                # Fallback to broader query if strict query returned nothing
                fallback_query = 'FROM "bmi@bestmediainfo.in"'
                status, search_data = mail.search(None, fallback_query)
                if status != "OK" or not search_data or not search_data[0]:
                    return {
                        "status": "success",
                        "checked_count": 0,
                        "ingested_count": 0,
                        "duplicate_count": 0,
                        "results": [],
                        "message": "Connected successfully to Gmail. No unread/matching newsletter emails found.",
                    }

            msg_ids = search_data[0].split()
            # Fetch latest emails first
            msg_ids.reverse()
            target_ids = msg_ids[:max_emails]

            checked_count = 0
            ingested_count = 0
            duplicate_count = 0
            results = []

            for msg_id in target_ids:
                checked_count += 1
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data:
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = _decode_mime_words(msg.get("Subject"))
                sender = _decode_mime_words(msg.get("From"))
                date_str = msg.get("Date", "")

                html_body, text_body = _extract_html_and_text(msg)
                if not html_body:
                    # If HTML part is absent, wrap plain text in simple HTML formatting
                    html_body = f"<html><body><pre>{text_body}</pre></body></html>"

                # Extract sender name and clean email
                sender_name = "Best Media Info"
                sender_email = "bmi@bestmediainfo.in"
                if "<" in sender and ">" in sender:
                    sender_name = sender.split("<")[0].strip().strip('"\'')
                    sender_email = sender.split("<")[1].split(">")[0].strip()
                elif "@" in sender:
                    sender_email = sender.strip()

                meta = {
                    "source_name": "Best Media Info" if "bestmediainfo" in sender.lower() else sender_name,
                    "sender_name": sender_name or "Newsletter Sender",
                    "sender_email": sender_email,
                    "email_subject": subject,
                    "raw_date": date_str,
                }

                # Ingest through MailerService (deduplication handled via SHA-256)
                res = mailer_service.process_email_html(html_body, metadata=meta)
                if res.get("status") == "duplicate" or res.get("is_duplicate"):
                    duplicate_count += 1
                else:
                    ingested_count += 1

                results.append({
                    "subject": subject,
                    "sender": sender,
                    "status": res.get("status"),
                    "article_count": res.get("article_count", 0),
                    "advertisement_count": res.get("advertisement_count", 0),
                    "mailer_id": res.get("data", {}).get("id") if res.get("data") else None,
                })

                if mark_as_read:
                    mail.store(msg_id, "+FLAGS", "\\Seen")

            return {
                "status": "success",
                "checked_count": checked_count,
                "ingested_count": ingested_count,
                "duplicate_count": duplicate_count,
                "results": results,
                "message": f"Gmail synchronization completed. Processed {checked_count} emails ({ingested_count} newly imported, {duplicate_count} existing duplicates).",
            }

        finally:
            try:
                if mail:
                    mail.close()
                    mail.logout()
            except Exception:
                pass


gmail_fetcher = GmailMailerFetcher()
