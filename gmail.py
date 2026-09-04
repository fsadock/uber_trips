#!/usr/bin/env python3
import base64
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from uber_trip_parser import parse_uber_receipt
import dlt

# Read-only is all we need. If you change scopes, delete token.json and re-auth.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_service(creds_file="credentials.json", token_file="token.json"):
    """Authenticate and return a Gmail API service object."""
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_file):
                raise FileNotFoundError(
                    f"Missing {creds_file}. See the SETUP notes at the top of this file."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def search_message_ids(service, query, max_results=500):
    """Return all message IDs matching a Gmail search query (handles paging)."""
    ids, page_token = [], None
    while True:
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token, maxResults=500)
            .execute()
        )
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token or len(ids) >= max_results:
            break
    return ids[:max_results]


def _header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode(data):
    if not data:
        return ""
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode(
        "utf-8", errors="replace"
    )


def _walk_body(payload):
    """Return (plain_text, html) by walking all MIME parts."""
    plain, html = "", ""
    stack = [payload]
    while stack:
        part = stack.pop()
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        if mime == "text/plain":
            plain += _decode(body.get("data", ""))
        elif mime == "text/html":
            html += _decode(body.get("data", ""))
        for sub in part.get("parts", []):
            stack.append(sub)
    return plain, html


def get_message(service, msg_id):
    """Fetch one message and return a flat dict."""
    msg = (
        service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    )
    payload = msg["payload"]
    headers = payload.get("headers", [])
    plain, html = _walk_body(payload)

    date_str = _header(headers, "Date")
    try:
        dt = parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        dt = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)

    return {
        "id": msg_id,
        "date": dt,
        "from": _header(headers, "From"),
        "subject": _header(headers, "Subject"),
        "snippet": msg.get("snippet", ""),
        "plain": plain,
        "html": html,
    }


# --- Uber-specific parsing -------------------------------------------------
# Brazilian receipts show amounts like "R$ 38,50". This grabs every R$ amount
# and treats the largest as the trip total — a heuristic. Once you see a real
# receipt, tighten this (e.g. anchor on the word "Total").
_MONEY = re.compile(r"R\$\s*([\d.]+,\d{2})")


def extract_fare(text):
    amounts = []
    for raw in _MONEY.findall(text or ""):
        amounts.append(float(raw.replace(".", "").replace(",", ".")))
    return max(amounts) if amounts else None


@dlt.resource(write_disposition="merge", primary_key="message_id")
def uber_trips(query="from:uber.com", max_results=50):

    service = get_service()
    ids = search_message_ids(service, query, max_results)

    for mid in ids:
        m = get_message(service, mid)
        body = m["plain"] or re.sub(
            r"<[^>]+>", " ", m["html"]
        )  # strip tags if only HTML
        parsed = parse_uber_receipt(body)
        if not (parsed.get("date") and parsed.get("total_brl")):
            continue
        yield {"message_id": mid, **parsed}


if __name__ == "__main__":
    # service = get_service()
    # ids = search_message_ids(service, "from:uber.com recibos da uber ", 5)
    # m = get_message(service, ids[0])
    # for href in re.findall(r'href="([^"]+)"', m["html"]):
    #     print(href)
    service = get_service()
    ids = search_message_ids(service, "from:uber.com", 200)
    print(len(ids), "emails found")
    for mid in ids:
        m = get_message(service, mid)
        print(mid, "|", m["subject"])
