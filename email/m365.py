"""
HexClaw — email/m365.py
=======================
Microsoft 365 / Graph API module.
Handles authentication, email traversal, and drafting.
"""

import os
import logging
import requests
from typing import List, Optional

log = logging.getLogger("hexclaw.email.m365")

class GraphServiceClient:
    """
    Simulated GraphServiceClient using direct REST calls.
    Avoids SDK installation issues on systems with path limits.
    """
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.token = self._authenticate()
        self.base_url = "https://graph.microsoft.com/v1.0/me"

    def _authenticate(self) -> str:
        """ROPC Flow (assuming App Email/Pass per PRD)."""
        # In a real scenario, this involves tenant_id, client_id, etc.
        # This is a shim for v1.0.
        log.info(f"Authenticating M365 for {self.email}...")
        return "fake_token_for_v1.0"

    def list_messages(self, folder: str = "inbox", limit: int = 10) -> List[dict]:
        """Fetch emails from a folder."""
        # Simulated API call
        return [
            {"id": "msg1", "subject": "Urgent: Breach detected", "sender": "security@target.com", "body": "We have a problem."},
            {"id": "msg2", "subject": "Invoice 123", "sender": "billing@target.com", "body": "Please pay immediately."}
        ]

    def create_draft(self, to: str, subject: str, content: str) -> str:
        """Create a draft reply."""
        log.info(f"Creating M365 draft to {to}")
        return "draft_id_789"

class M365Engine:
    def __init__(self):
        self.client = None
        email = os.getenv("M365_EMAIL")
        pw = os.getenv("M365_PASS")
        if email and pw:
            self.client = GraphServiceClient(email, pw)

    def classify_and_label(self, domain: str):
        """Classify emails from a specific domain."""
        if not self.client: return []
        messages = self.client.list_messages()
        results = []
        for msg in messages:
            if domain in msg.get("sender", ""):
                results.append({"id": msg["id"], "label": "phishing_target"})
        return results

    def draft_reply(self, msg_id: str, content: str):
        """Draft a reply string."""
        if not self.client: return None
        return self.client.create_draft("operator@hexclaw.ai", "Re: Investigation", content)
