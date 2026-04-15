"""
Gmail API integration.
Handles sending emails and polling inbox for client replies.

Credentials flow:
  1. Owner completes OAuth via /auth/gmail/callback (future)
  2. Token stored in DB (future — for now read from .env)
  3. This module uses the token to send and poll

For local dev: if GMAIL_CLIENT_ID is empty, send() logs
a warning and skips the actual API call — message is still
written to communication_logs.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"


async def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    access_token: str,
) -> dict:
    """
    Sends an email via Gmail API using an OAuth access token.
    Returns the sent message metadata from Gmail.
    Raises httpx.HTTPStatusError on failure.
    """
    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{GMAIL_API_BASE}/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()


async def poll_inbox_for_replies(
    access_token: str,
    after_timestamp: int,  # Unix timestamp — only fetch messages after this
) -> list[dict]:
    """
    Polls Gmail inbox for messages received after a given timestamp.
    Returns a list of message dicts with id, subject, from, body, date.
    Used by the Celery polling job.
    """
    async with httpx.AsyncClient() as client:
        # Search for messages after the given timestamp
        query = f"after:{after_timestamp} in:inbox"
        list_response = await client.get(
            f"{GMAIL_API_BASE}/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": query, "maxResults": 50},
            timeout=15,
        )
        list_response.raise_for_status()
        message_list = list_response.json().get("messages", [])

        if not message_list:
            return []

        # Fetch full content of each message
        messages = []
        for msg_ref in message_list:
            detail_response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages/{msg_ref['id']}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"format": "full"},
                timeout=15,
            )
            if detail_response.status_code == 200:
                messages.append(detail_response.json())

        return messages


def extract_message_body(gmail_message: dict) -> str:
    """
    Extracts plain text body from a Gmail message payload.
    Handles both simple and multipart messages.
    """
    import base64

    payload = gmail_message.get("payload", {})
    parts = payload.get("parts", [])

    if parts:
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    return ""


def extract_header(gmail_message: dict, name: str) -> str:
    """Extracts a specific header value from a Gmail message."""
    headers = gmail_message.get("payload", {}).get("headers", [])
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""