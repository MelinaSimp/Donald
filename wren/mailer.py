"""Mailer seam — "give me a recipient, subject, body; send it."

A real side effect behind the Tier 6 confirmation gate. SMTP keeps it
provider-agnostic (Gmail app password, Fastmail, your own server, ...). Like the
model/STT/TTS seams, the rest of the harness depends only on `Mailer.send`, so
the provider can change in one place. Credentials live in the environment
(SMTP_USERNAME / SMTP_PASSWORD), never in code; connection details in config.yaml.

build_mailer returns None when email isn't configured, so send_message can give
an honest "not set up yet" message instead of pretending to send.
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> str: ...


@dataclass
class SMTPMailer:
    host: str
    port: int
    from_addr: str
    username: str | None
    password: str | None
    use_tls: bool = True

    def send(self, to: str, subject: str, body: str) -> str:
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject or "(no subject)"
        msg.set_content(body)

        if self.port == 465:  # implicit TLS
            with smtplib.SMTP_SSL(self.host, self.port, context=ssl.create_default_context()) as s:
                self._login_send(s, msg)
        else:
            with smtplib.SMTP(self.host, self.port) as s:
                if self.use_tls:
                    s.starttls(context=ssl.create_default_context())
                self._login_send(s, msg)
        return f"Sent to {to}: {subject or '(no subject)'}"

    def _login_send(self, s: smtplib.SMTP, msg: EmailMessage) -> None:
        if self.username and self.password:
            s.login(self.username, self.password)
        s.send_message(msg)


def build_mailer(config) -> Mailer | None:
    host = config.get("email.smtp_host", "")
    from_addr = config.get("email.from_addr", "")
    if not host or not from_addr:
        return None  # not configured — send_message will say so plainly
    return SMTPMailer(
        host=host,
        port=int(config.get("email.smtp_port", 587)),
        from_addr=from_addr,
        username=config.secret("SMTP_USERNAME"),
        password=config.secret("SMTP_PASSWORD"),
        use_tls=bool(config.get("email.use_tls", True)),
    )
