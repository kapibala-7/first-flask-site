"""生日提醒邮件的 SMTP 配置校验与发送。"""

from __future__ import annotations

import smtplib
import ssl
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from typing import Any, Mapping


class MailConfigurationError(ValueError):
    """邮件提醒未配置或 SMTP 参数无效。"""


def _tls_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.casefold() in {"true", "1", "yes", "on"}:
        return True
    if isinstance(value, str) and value.casefold() in {"false", "0", "no", "off"}:
        return False
    raise MailConfigurationError("invalid_tls_setting")


def validate_mail_config(config: Mapping[str, Any]) -> tuple[str, int, bool, bool]:
    required = (
        "MAIL_SERVER",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_DEFAULT_SENDER",
        "ADMIN_EMAIL",
    )
    if any(not str(config.get(key, "")).strip() for key in required):
        raise MailConfigurationError("missing_required_setting")

    try:
        port = int(config.get("MAIL_PORT", 587))
    except (TypeError, ValueError) as error:
        raise MailConfigurationError("invalid_mail_port") from error
    if not 1 <= port <= 65535:
        raise MailConfigurationError("invalid_mail_port")

    server = str(config["MAIL_SERVER"]).strip()
    use_tls = _tls_enabled(config.get("MAIL_USE_TLS", True))
    use_ssl = _tls_enabled(config.get("MAIL_USE_SSL", False))
    if use_tls and use_ssl:
        raise MailConfigurationError("tls_and_ssl_are_mutually_exclusive")
    return server, port, use_tls, use_ssl


def send_birthday_notification(
    config: Mapping[str, Any],
    event: Mapping[str, Any],
) -> None:
    """向单个管理员发送指定生日事件；异常由调用方记录并持久化。"""
    server, port, use_tls, use_ssl = validate_mail_config(config)
    triggered_at = datetime.fromisoformat(str(event["triggered_at"]))
    birth_date = date.fromisoformat(str(event["birth_date"]))
    sender = str(config["MAIL_DEFAULT_SENDER"]).strip()
    recipient = str(config["ADMIN_EMAIL"]).strip()
    event_id = int(event["id"])

    message = EmailMessage()
    message["Subject"] = "有人在生日当天访问了《答案之书》"
    message["From"] = sender
    message["To"] = recipient
    sender_domain = sender.rpartition("@")[2] or "answerbook.local"
    message["Message-ID"] = make_msgid(
        idstring=f"birthday-event-{event_id}", domain=sender_domain
    )
    message["Date"] = format_datetime(triggered_at)
    message.set_content(
        "\n".join(
            (
                "《答案之书》生日访问提醒",
                "",
                "有访客在生日当天进入网站，并触发了生日祝福流程。",
                f"访客姓名：{event['name']}",
                f"访客生日：{birth_date.month} 月 {birth_date.day} 日",
                f"访问时间：{triggered_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                "",
                "此邮件仅发送给网站管理员。",
            )
        )
    )

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    smtp_options: dict[str, Any] = {"timeout": 10}
    if use_ssl:
        smtp_options["context"] = ssl.create_default_context()
    with smtp_class(server, port, **smtp_options) as smtp:
        if not use_ssl:
            smtp.ehlo()
            if use_tls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
        smtp.login(
            str(config["MAIL_USERNAME"]).strip(),
            str(config["MAIL_PASSWORD"]),
        )
        refused = smtp.send_message(message, to_addrs=[recipient])
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
