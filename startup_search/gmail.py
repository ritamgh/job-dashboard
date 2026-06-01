from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass
from .config import get_settings


@dataclass
class GmailSendResult:
    sent: bool
    dry_run: bool = False
    message_id: str | None = None
    thread_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            'sent': self.sent,
            'dry_run': self.dry_run,
            'message_id': self.message_id,
            'thread_id': self.thread_id,
            'error': self.error,
        }


def send_email(to: str, subject: str, body: str) -> GmailSendResult:
    settings = get_settings()
    if not settings.gmail_mcp_command:
        return GmailSendResult(sent=False, dry_run=True, error='Gmail MCP command is not configured')
    payload = {'to': to, 'subject': subject, 'body': body}
    try:
        proc = subprocess.run(
            settings.gmail_mcp_command,
            input=json.dumps(payload),
            text=True,
            shell=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:
        return GmailSendResult(sent=False, error=str(exc))
    if proc.returncode != 0:
        return GmailSendResult(sent=False, error=(proc.stderr or proc.stdout or 'Gmail MCP command failed').strip())
    try:
        data = json.loads(proc.stdout or '{}')
    except json.JSONDecodeError:
        data = {}
    return GmailSendResult(sent=True, message_id=data.get('message_id') or data.get('id'), thread_id=data.get('thread_id'))
