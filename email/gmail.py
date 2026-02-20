"""
HexClaw — email/gmail.py
=======================
Gmail API module using google-api-python-client.
"""

import os
import logging
from typing import List, Optional

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
except ImportError:
    build = None

log = logging.getLogger("hexclaw.email.gmail")

class GmailEngine:
    def __init__(self):
        self.service = None
        # Assuming token.json exists per standard Google API usage
        token_path = "token.json"
        if os.path.exists(token_path) and build:
            creds = Credentials.from_authorized_user_file(token_path)
            self.service = build('gmail', 'v1', credentials=creds)

    def list_messages(self, query: str = "") -> List[dict]:
        """List messages matching query."""
        if not self.service: return []
        results = self.service.users().messages().list(userId='me', q=query).execute()
        return results.get('messages', [])

    def get_message(self, msg_id: str) -> dict:
        if not self.service: return {}
        return self.service.users().messages().get(userId='me', id=msg_id).execute()

    def create_draft(self, raw_message: str) -> str:
        """Create a draft from base64 encoded RFC822 message."""
        if not self.service: return ""
        draft = {'message': {'raw': raw_message}}
        res = self.service.users().drafts().create(userId='me', body=draft).execute()
        return res.get('id', '')

def new_inbox(purpose: str) -> str:
    """Monitor for a new inbox/alias creation."""
    log.info(f"Monitoring for new inbox with purpose: {purpose}")
    return f"alias_{purpose}@hexclaw.ai"
