# -*- coding: utf-8 -*-
"""《答案之书》Flask 应用：用户登记、生日祝福与答案接口。"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from answer_engine import find_category, normalize_question, resolve_answer
from answer_data import ANSWER_CATEGORIES, EASTER_EGGS, SPECIAL_QUESTIONS
from birthday_mail import (
    MailConfigurationError,
    send_birthday_notification,
    validate_mail_config,
)
from storage import (
    approved_special_answer,
    claim_birthday_notification,
    create_user,
    create_birthday_event,
    discovered_egg_ids,
    finish_birthday_notification,
    get_birthday_event,
    find_user_by_token,
    has_seen_birthday,
    initialize_database,
    issue_token,
    mark_birthday_seen,
    match_users,
    public_user,
    record_egg_discovery,
    record_visit,
    get_special_question_review,
    list_special_question_reviews,
    review_special_question,
    submit_special_question,
    list_birthday_events,
)

load_dotenv()

NAME_LIMIT = 40
QUESTION_LIMIT = 500
MAX_BIRTHDAY_EMAIL_ATTEMPTS = 3
BIRTHDAY_COPY = "今天是属于你的日子。愿新的一岁有温柔相伴，也有勇气走向你想去的地方。"


def normalize_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).strip().casefold()


def today_for_app(app: Flask) -> date:
    try:
        timezone = ZoneInfo(app.config["TIMEZONE"])
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(
            f"无效的 APP_TIMEZONE 配置：{app.config['TIMEZONE']}"
        ) from error
    return datetime.now(timezone).date()


def bearer_token() -> str | None:
    authorization = request.headers.get("Authorization", "")
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.casefold() != "bearer" or not token.strip():
        return ""
    return token.strip()


def current_user(database_path: str) -> sqlite3.Row | None:
    token = bearer_token()
    if token is None or token == "":
        return None
    return find_user_by_token(database_path, token)


def birthday_is_today(birth_date: date, today: date) -> bool:
    """闰年生日在非闰年按 2 月 28 日庆祝，避免当年没有对应日期。"""
    if birth_date.month == 2 and birth_date.day == 29 and today.month == 2:
        return today.day == (29 if _is_leap_year(today.year) else 28)
    return (birth_date.month, birth_date.day) == (today.month, today.day)


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def birthday_state(app: Flask, database_path: str, user: Any) -> tuple[date, bool]:
    today = today_for_app(app)
    birth_date = date.fromisoformat(str(user["birth_date"]))
    is_birthday = birthday_is_today(birth_date, today)
    pending = is_birthday and not has_seen_birthday(
        database_path, int(user["id"]), today.isoformat()
    )
    return today, pending


def deliver_birthday_notification(
    app: Flask,
    event_id: int,
    *,
    retry_failed: bool = False,
) -> bool | None:
    """原子领取并发送提醒；返回 None 表示事件未能领取。"""
    database_path = app.config["DATABASE_PATH"]
    attempt = claim_birthday_notification(
        database_path,
        event_id,
        retry_failed=retry_failed,
        max_attempts=MAX_BIRTHDAY_EMAIL_ATTEMPTS,
    )
    if attempt is None:
        return None

    event = get_birthday_event(database_path, event_id)
    if event is None:
        app.logger.error("Birthday email event disappeared after claim (event_id=%s)", event_id)
        return False

    try:
        send_birthday_notification(app.config, event)
    except Exception as error:
        try:
            finish_birthday_notification(
                database_path,
                event_id,
                attempt,
                sent=False,
                error_code=type(error).__name__,
            )
        except sqlite3.Error:
            app.logger.exception(
                "Could not persist birthday email failure (event_id=%s, attempt=%s)",
                event_id,
                attempt,
            )
        app.logger.warning(
            "Birthday email failed (event_id=%s, attempt=%s, error=%s)",
            event_id,
            attempt,
            type(error).__name__,
        )
        return False

    try:
        updated = finish_birthday_notification(
            database_path, event_id, attempt, sent=True
        )
    except sqlite3.Error:
        app.logger.exception(
            "SMTP accepted birthday email but sent status could not be persisted "
            "(event_id=%s, attempt=%s)",
            event_id,
            attempt,
        )
        return False
    if not updated:
        app.logger.error(
            "Birthday email accepted but event state could not be marked sent (event_id=%s)",
            event_id,
        )
        return False
    app.logger.info("Birthday email accepted by SMTP (event_id=%s)", event_id)
    return True


def valid_name(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    name = unicodedata.normalize("NFC", value).strip()
    if (
        not name
        or len(name) > NAME_LIMIT
        or any(unicodedata.category(character).startswith("C") for character in name)
    ):
        return None
    return name, normalize_name(name)


def valid_birth_date(value: Any, today: date) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        birth_date = date.fromisoformat(value)
    except ValueError:
        return None
    if birth_date.isoformat() != value or birth_date > today or birth_date.year < 1900:
        return None
    return birth_date


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE_PATH=os.environ.get(
            "ANSWERBOOK_DATABASE", str(Path(app.instance_path) / "answerbook.sqlite3")
        ),
        TIMEZONE=os.environ.get(
            "APP_TIMEZONE", os.environ.get("ANSWERBOOK_TIMEZONE", "Asia/Shanghai")
        ),
        ADMIN_TOKEN=os.environ.get("ANSWERBOOK_ADMIN_TOKEN", ""),
        MAIL_SERVER=os.environ.get("MAIL_SERVER", ""),
        MAIL_PORT=os.environ.get("MAIL_PORT", "587"),
        MAIL_USE_TLS=os.environ.get("MAIL_USE_TLS", "true"),
        MAIL_USE_SSL=os.environ.get("MAIL_USE_SSL", "false"),
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME", ""),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD", ""),
        MAIL_DEFAULT_SENDER=os.environ.get("MAIL_DEFAULT_SENDER", ""),
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL", ""),
    )
    if test_config:
        app.config.update(test_config)
    initialize_database(app.config["DATABASE_PATH"])

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.post("/api/users/register")
    def register_user():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "message": "请填写姓名和生日。"}), 400

        name_data = valid_name(payload.get("name"))
        birth_date = valid_birth_date(payload.get("birth_date"), today_for_app(app))
        if name_data is None:
            return jsonify(
                {"ok": False, "message": f"姓名请控制在 1 至 {NAME_LIMIT} 个字符内。"}
            ), 400
        if birth_date is None:
            return jsonify({"ok": False, "message": "请输入有效且不晚于今天的生日。"}), 400

        token = secrets.token_urlsafe(32)
        recovery_code = secrets.token_urlsafe(12).upper()
        try:
            user_id = create_user(
                app.config["DATABASE_PATH"],
                name_data[0],
                name_data[1],
                birth_date.isoformat(),
                token,
                recovery_code,
            )
        except Exception:
            app.logger.exception("创建用户记录失败")
            return jsonify({"ok": False, "message": "登记暂时失败，请稍后重试。"}), 500

        return jsonify(
            {
                "ok": True,
                "token": token,
                "recovery_code": recovery_code,
                "user": {"id": user_id, "name": name_data[0]},
            }
        ), 201

    @app.post("/api/users/identify")
    def identify_user():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "message": "请填写姓名和生日。"}), 400

        name_data = valid_name(payload.get("name"))
        birth_date = valid_birth_date(payload.get("birth_date"), today_for_app(app))
        if name_data is None or birth_date is None:
            return jsonify({"ok": False, "message": "姓名或生日格式不正确。"}), 400

        matches = match_users(
            app.config["DATABASE_PATH"], name_data[1], birth_date.isoformat()
        )
        recovery_code = payload.get("recovery_code", "")
        if not isinstance(recovery_code, str):
            return jsonify({"ok": False, "message": "识别失败，请检查信息后重试。"}), 401

        if len(matches) > 1:
            if not recovery_code:
                return jsonify(
                    {
                        "ok": False,
                        "needs_recovery_code": True,
                        "message": "发现姓名与生日相同的登记，请输入登记时保存的识别码。",
                    }
                ), 409
            recovery_hash = hashlib.sha256(
                recovery_code.strip().upper().encode("utf-8")
            ).hexdigest()
            matches = [
                user
                for user in matches
                if hmac.compare_digest(str(user["recovery_code_hash"]), recovery_hash)
            ]
        elif matches and recovery_code:
            recovery_hash = hashlib.sha256(
                recovery_code.strip().upper().encode("utf-8")
            ).hexdigest()
            if not hmac.compare_digest(
                str(matches[0]["recovery_code_hash"]), recovery_hash
            ):
                matches = []

        if len(matches) != 1:
            return jsonify({"ok": False, "message": "未能识别这条登记，请检查信息或识别码。"}), 401

        token = secrets.token_urlsafe(32)
        issue_token(app.config["DATABASE_PATH"], int(matches[0]["id"]), token)
        return jsonify(
            {
                "ok": True,
                "token": token,
                "user": {"id": int(matches[0]["id"]), "name": name_data[0]},
            }
        )

    @app.get("/api/users/me")
    def get_current_user():
        token = bearer_token()
        if token == "":
            return jsonify({"ok": False, "message": "访问凭证无效。"}), 401
        user = current_user(app.config["DATABASE_PATH"])
        if user is None:
            return jsonify({"ok": False, "message": "请先登记或重新识别。"}), 401

        today = today_for_app(app)
        record_visit(app.config["DATABASE_PATH"], int(user["id"]), today.isoformat())
        user = find_user_by_token(app.config["DATABASE_PATH"], token)
        _, birthday_pending = birthday_state(app, app.config["DATABASE_PATH"], user)
        if birthday_pending:
            try:
                event_id, _ = create_birthday_event(
                    app.config["DATABASE_PATH"],
                    int(user["id"]),
                    today.isoformat(),
                    datetime.now(ZoneInfo(app.config["TIMEZONE"])).isoformat(),
                )
                deliver_birthday_notification(app, event_id)
            except sqlite3.Error:
                app.logger.exception(
                    "Could not record birthday visit event (user_id=%s)", user["id"]
                )
        return jsonify(
            {
                "ok": True,
                "user": public_user(user),
                "birthday_pending": birthday_pending,
                "birthday_message": BIRTHDAY_COPY if birthday_pending else None,
                "discovered_eggs": sorted(
                    discovered_egg_ids(app.config["DATABASE_PATH"], int(user["id"]))
                ),
            }
        )

    @app.post("/api/users/birthday/ack")
    def acknowledge_birthday():
        token = bearer_token()
        if token == "":
            return jsonify({"ok": False, "message": "访问凭证无效。"}), 401
        user = current_user(app.config["DATABASE_PATH"])
        if user is None:
            return jsonify({"ok": False, "message": "请先登记或重新识别。"}), 401

        today, pending = birthday_state(app, app.config["DATABASE_PATH"], user)
        if not birthday_is_today(date.fromisoformat(str(user["birth_date"])), today):
            return jsonify({"ok": False, "message": "今天不是登记的生日日期。"}), 409
        mark_birthday_seen(app.config["DATABASE_PATH"], int(user["id"]), today.isoformat())
        return jsonify({"ok": True, "birthday_pending": False, "was_pending": pending})

    @app.post("/api/special-questions")
    def submit_question_for_review():
        token = bearer_token()
        if token == "":
            return jsonify({"ok": False, "message": "访问凭证无效。"}), 401
        user = current_user(app.config["DATABASE_PATH"])
        if user is None:
            return jsonify({"ok": False, "message": "请先登记或重新识别。"}), 401

        payload = request.get_json(silent=True)
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip():
            return jsonify({"ok": False, "message": "请填写要申请审核的问题。"}), 400
        question = question.strip()
        if len(question) > 200:
            return jsonify({"ok": False, "message": "审核申请请控制在 200 个字符以内。"}), 400

        normalized = normalize_question(question)
        if normalized in SPECIAL_QUESTIONS:
            return jsonify({"ok": False, "message": "这条问题已经有正式答案。"}), 409
        try:
            request_id = submit_special_question(
                app.config["DATABASE_PATH"],
                int(user["id"]),
                question,
                normalized,
            )
        except sqlite3.IntegrityError:
            return jsonify(
                {"ok": False, "message": "这条问题已经提交过审核，请稍后查看状态。"}
            ), 409
        return jsonify(
            {
                "ok": True,
                "request_id": request_id,
                "status": "pending",
                "message": "已进入人工审核。审核通过前，它不会被当作正式答案使用。",
            }
        ), 202

    @app.get("/api/special-questions/<int:request_id>")
    def get_review_status(request_id: int):
        token = bearer_token()
        if token == "":
            return jsonify({"ok": False, "message": "访问凭证无效。"}), 401
        user = current_user(app.config["DATABASE_PATH"])
        if user is None:
            return jsonify({"ok": False, "message": "请先登记或重新识别。"}), 401
        review = get_special_question_review(
            app.config["DATABASE_PATH"], request_id, int(user["id"])
        )
        if review is None:
            return jsonify({"ok": False, "message": "未找到这条审核申请。"}), 404
        return jsonify(
            {
                "ok": True,
                "review": {
                    "id": int(review["id"]),
                    "question": str(review["question"]),
                    "status": str(review["status"]),
                    "review_note": review["review_note"],
                    "created_at": str(review["created_at"]),
                    "reviewed_at": review["reviewed_at"],
                },
            }
        )

    def require_admin():
        configured_token = app.config["ADMIN_TOKEN"]
        if not configured_token:
            return jsonify(
                {
                    "ok": False,
                    "message": "管理员审核尚未配置；请设置 ANSWERBOOK_ADMIN_TOKEN。",
                }
            ), 503
        supplied_token = bearer_token()
        if supplied_token in (None, "") or not hmac.compare_digest(
            supplied_token, configured_token
        ):
            return jsonify({"ok": False, "message": "管理员凭证无效。"}), 401
        return None

    @app.get("/api/admin/birthday-events")
    def admin_list_birthday_events():
        denial = require_admin()
        if denial is not None:
            return denial
        status = request.args.get("status")
        if status not in {None, "pending", "sent", "failed"}:
            return jsonify({"ok": False, "message": "通知状态参数无效。"}), 400
        events = list_birthday_events(app.config["DATABASE_PATH"], status)
        return jsonify(
            {
                "ok": True,
                "events": [
                    {
                        "id": int(event["id"]),
                        "user_id": int(event["user_id"]),
                        "name": str(event["name"]),
                        "birth_month_day": date.fromisoformat(
                            str(event["birth_date"])
                        ).strftime("%m-%d"),
                        "event_date": str(event["event_date"]),
                        "triggered_at": str(event["triggered_at"]),
                        "notification_status": str(event["notification_status"]),
                        "attempts": int(event["attempts"]),
                        "last_attempt_at": event["last_attempt_at"],
                        "sent_at": event["sent_at"],
                        "last_error_code": event["last_error_code"],
                    }
                    for event in events
                ],
            }
        )

    @app.post("/api/admin/birthday-events/<int:event_id>/retry")
    def admin_retry_birthday_email(event_id: int):
        denial = require_admin()
        if denial is not None:
            return denial
        event = get_birthday_event(app.config["DATABASE_PATH"], event_id)
        if event is None:
            return jsonify({"ok": False, "message": "未找到这条生日提醒事件。"}), 404
        if event["notification_status"] != "failed":
            return jsonify(
                {
                    "ok": False,
                    "message": "只有发送失败的事件可以由管理员重试。",
                    "notification_status": str(event["notification_status"]),
                }
            ), 409
        if int(event["attempts"]) >= MAX_BIRTHDAY_EMAIL_ATTEMPTS:
            return jsonify(
                {"ok": False, "message": "该提醒已达到最大重试次数，请检查 SMTP 配置和服务器日志。"}
            ), 429
        try:
            validate_mail_config(app.config)
        except MailConfigurationError:
            return jsonify(
                {
                    "ok": False,
                    "message": "邮件配置不完整或无效；请检查服务器环境变量后重试。",
                }
            ), 503

        result = deliver_birthday_notification(app, event_id, retry_failed=True)
        event = get_birthday_event(app.config["DATABASE_PATH"], event_id)
        if result is None:
            return jsonify(
                {
                    "ok": False,
                    "message": "该事件当前不可重试；只有发送失败的事件可以由管理员重试。",
                    "notification_status": str(event["notification_status"]),
                }
            ), 409
        if not result:
            return jsonify(
                {
                    "ok": False,
                    "message": "邮件发送失败；请检查 SMTP 配置和服务器日志。",
                    "notification_status": str(event["notification_status"]),
                    "attempts": int(event["attempts"]),
                }
            ), 502
        return jsonify(
            {
                "ok": True,
                "notification_status": str(event["notification_status"]),
                "attempts": int(event["attempts"]),
            }
        )

    @app.get("/api/admin/special-questions")
    def admin_list_special_questions():
        denial = require_admin()
        if denial is not None:
            return denial
        status = request.args.get("status", "pending")
        if status not in {"pending", "approved", "rejected"}:
            return jsonify({"ok": False, "message": "审核状态参数无效。"}), 400
        reviews = list_special_question_reviews(app.config["DATABASE_PATH"], status)
        return jsonify(
            {
                "ok": True,
                "reviews": [
                    {
                        "id": int(review["id"]),
                        "user_id": int(review["user_id"]),
                        "question": str(review["question"]),
                        "answer": review["answer"],
                        "status": str(review["status"]),
                        "review_note": review["review_note"],
                        "created_at": str(review["created_at"]),
                    }
                    for review in reviews
                ],
            }
        )

    @app.patch("/api/admin/special-questions/<int:request_id>")
    def admin_review_special_question(request_id: int):
        denial = require_admin()
        if denial is not None:
            return denial
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "message": "请提交审核决定。"}), 400
        status = payload.get("status")
        answer = payload.get("answer")
        review_note = payload.get("review_note")
        if status not in {"approved", "rejected"}:
            return jsonify({"ok": False, "message": "审核决定必须是通过或拒绝。"}), 400
        if status == "approved" and (
            not isinstance(answer, str) or not answer.strip() or len(answer.strip()) > 500
        ):
            return jsonify(
                {"ok": False, "message": "通过审核时必须填写不超过 500 字的正式答案。"}
            ), 400
        if review_note is not None and (
            not isinstance(review_note, str) or len(review_note) > 500
        ):
            return jsonify({"ok": False, "message": "审核说明最多 500 字。"}), 400

        updated = review_special_question(
            app.config["DATABASE_PATH"],
            request_id,
            status,
            answer.strip() if isinstance(answer, str) and status == "approved" else None,
            review_note.strip() if isinstance(review_note, str) else None,
        )
        if not updated:
            return jsonify(
                {"ok": False, "message": "申请不存在或已被审核，状态未发生变化。"}
            ), 409
        return jsonify({"ok": True, "status": status})

    @app.post("/api/answer")
    def get_answer():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "message": "请提交有效的问题。"}), 400
        question = payload.get("question")
        if not isinstance(question, str):
            return jsonify({"ok": False, "message": "问题格式不正确。"}), 400
        question = question.strip()
        if not question:
            return jsonify({"ok": False, "message": "请先在心里想好问题，再写下来。"}), 400
        if len(question) > QUESTION_LIMIT:
            return jsonify(
                {"ok": False, "message": f"问题有些长，请控制在 {QUESTION_LIMIT} 个字符以内。"}
            ), 400

        token = bearer_token()
        if token == "":
            return jsonify({"ok": False, "message": "访问凭证无效，请重新识别。"}), 401
        user = current_user(app.config["DATABASE_PATH"]) if token else None
        if token and user is None:
            return jsonify({"ok": False, "message": "访问凭证已失效，请重新识别。"}), 401

        birthday_pending = False
        visit_count = 0
        discovered: set[str] = set()
        if user is not None:
            _, birthday_pending = birthday_state(app, app.config["DATABASE_PATH"], user)
            visit_count = int(user["visit_count"])
            discovered = discovered_egg_ids(
                app.config["DATABASE_PATH"], int(user["id"])
            )

        normalized_question = normalize_question(question)
        approved_answer = approved_special_answer(
            app.config["DATABASE_PATH"], normalized_question
        )
        result = resolve_answer(
            question,
            birthday_pending=birthday_pending,
            visit_count=visit_count,
            discovered_eggs=discovered,
            approved_special_questions=(
                {normalized_question: approved_answer} if approved_answer else {}
            ),
        )
        newly_discovered = False
        if (
            user is not None
            and result.get("is_easter_egg")
            and result.get("save_discovery")
            and result.get("egg_id")
        ):
            newly_discovered = record_egg_discovery(
                app.config["DATABASE_PATH"], int(user["id"]), result["egg_id"]
            )

        return jsonify(
            {
                "ok": True,
                "answer": result["answer"],
                "category": result["category"],
                "is_easter_egg": result["is_easter_egg"],
                "egg_id": result.get("egg_id"),
                "egg_tier": result.get("egg_tier"),
                "egg_discovered": newly_discovered,
                "priority": result.get("priority"),
                "effect": result.get("effect", "answer"),
                "sound": result.get("sound", "answer"),
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("ANSWERBOOK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
