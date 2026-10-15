"""SQLite 持久化：用户资料、回访凭证、生日祝福状态和彩蛋发现记录。"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def connect(database_path: str) -> Iterator[sqlite3.Connection]:
    """创建启用外键约束的数据库连接。"""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: str) -> None:
    """以可重复执行的 CREATE TABLE 初始化，不覆盖已有记录。"""
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                birth_date TEXT NOT NULL,
                recovery_code_hash TEXT NOT NULL,
                visit_count INTEGER NOT NULL DEFAULT 0,
                last_visit_date TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_name_birth
                ON users (normalized_name, birth_date);
            CREATE TABLE IF NOT EXISTS user_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS birthday_greetings (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                greeting_date TEXT NOT NULL,
                PRIMARY KEY (user_id, greeting_date)
            );
            CREATE TABLE IF NOT EXISTS birthday_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                event_date TEXT NOT NULL,
                triggered_at TEXT NOT NULL,
                notification_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (notification_status IN ('pending', 'sent', 'failed')),
                attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                last_attempt_at TEXT,
                sent_at TEXT,
                last_error_code TEXT,
                UNIQUE (user_id, event_date)
            );
            CREATE INDEX IF NOT EXISTS idx_birthday_events_status_date
                ON birthday_events (notification_status, event_date);
            CREATE TABLE IF NOT EXISTS discovered_eggs (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                egg_id TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                PRIMARY KEY (user_id, egg_id)
            );
            CREATE TABLE IF NOT EXISTS special_question_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                normalized_question TEXT NOT NULL UNIQUE,
                answer TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
                review_note TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            );
            """
        )


def create_birthday_event(
    database_path: str,
    user_id: int,
    event_date: str,
    triggered_at: str,
) -> tuple[int, bool]:
    """按用户和本地日期幂等创建生日访问事件。"""
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO birthday_events (user_id, event_date, triggered_at)
            VALUES (?, ?, ?)
            """,
            (user_id, event_date, triggered_at),
        )
        created = cursor.rowcount == 1
        row = connection.execute(
            """
            SELECT id FROM birthday_events
            WHERE user_id = ? AND event_date = ?
            """,
            (user_id, event_date),
        ).fetchone()
        if row is None:
            raise RuntimeError("生日访问事件写入后无法读取。")
        return int(row["id"]), created


def claim_birthday_notification(
    database_path: str,
    event_id: int,
    *,
    retry_failed: bool = False,
    max_attempts: int = 3,
) -> int | None:
    """原子领取一次邮件发送；仅新事件或受控的失败重试可领取。"""
    status = "failed" if retry_failed else "pending"
    attempt_condition = "attempts < ?" if retry_failed else "attempts = 0"
    parameters: tuple[Any, ...] = (
        datetime.now(timezone.utc).isoformat(),
        event_id,
        status,
    )
    if retry_failed:
        parameters += (max_attempts,)
    with connect(database_path) as connection:
        cursor = connection.execute(
            f"""
            UPDATE birthday_events
            SET notification_status = 'pending',
                attempts = attempts + 1,
                last_attempt_at = ?,
                last_error_code = NULL
            WHERE id = ?
              AND notification_status = ?
              AND {attempt_condition}
            """,
            parameters,
        )
        if cursor.rowcount != 1:
            return None
        row = connection.execute(
            "SELECT attempts FROM birthday_events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("已领取的生日邮件事件不存在。")
        return int(row["attempts"])


def finish_birthday_notification(
    database_path: str,
    event_id: int,
    attempt: int,
    *,
    sent: bool,
    error_code: str | None = None,
) -> bool:
    """仅在 SMTP 接受邮件后标记 sent；错误只保存非敏感类型码。"""
    now = datetime.now(timezone.utc).isoformat()
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE birthday_events
            SET notification_status = ?,
                sent_at = ?,
                last_error_code = ?
            WHERE id = ? AND attempts = ? AND notification_status = 'pending'
            """,
            (
                "sent" if sent else "failed",
                now if sent else None,
                None if sent else (error_code or "delivery_failed")[:80],
                event_id,
                attempt,
            ),
        )
        return cursor.rowcount == 1


def get_birthday_event(
    database_path: str, event_id: int
) -> sqlite3.Row | None:
    with connect(database_path) as connection:
        return connection.execute(
            """
            SELECT birthday_events.*, users.name, users.birth_date
            FROM birthday_events
            JOIN users ON users.id = birthday_events.user_id
            WHERE birthday_events.id = ?
            """,
            (event_id,),
        ).fetchone()


def list_birthday_events(
    database_path: str, status: str | None = None, limit: int = 100
) -> list[sqlite3.Row]:
    with connect(database_path) as connection:
        if status is None:
            rows = connection.execute(
                """
                SELECT birthday_events.*, users.name, users.birth_date
                FROM birthday_events
                JOIN users ON users.id = birthday_events.user_id
                ORDER BY birthday_events.event_date DESC, birthday_events.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            rows = connection.execute(
                """
                SELECT birthday_events.*, users.name, users.birth_date
                FROM birthday_events
                JOIN users ON users.id = birthday_events.user_id
                WHERE notification_status = ?
                ORDER BY birthday_events.event_date DESC, birthday_events.id DESC
                LIMIT ?
                """,
                (status, limit),
            )
        return list(rows.fetchall())


def hash_credential(value: str) -> str:
    """数据库仅保存凭证摘要，不保存可直接重放的原始令牌。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def find_user_by_token(database_path: str, token: str) -> sqlite3.Row | None:
    token_hash = hash_credential(token)
    with connect(database_path) as connection:
        return connection.execute(
            """
            SELECT users.*
            FROM users
            JOIN user_tokens ON user_tokens.user_id = users.id
            WHERE user_tokens.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()


def create_user(
    database_path: str,
    name: str,
    normalized_name: str,
    birth_date: str,
    token: str,
    recovery_code: str,
) -> int:
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (
                name, normalized_name, birth_date, recovery_code_hash, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                name,
                normalized_name,
                birth_date,
                hash_credential(recovery_code),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        user_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO user_tokens (token_hash, user_id, created_at)
            VALUES (?, ?, ?)
            """,
            (
                hash_credential(token),
                user_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return user_id


def match_users(
    database_path: str, normalized_name: str, birth_date: str
) -> list[sqlite3.Row]:
    with connect(database_path) as connection:
        return list(
            connection.execute(
                """
                SELECT id, recovery_code_hash
                FROM users
                WHERE normalized_name = ? AND birth_date = ?
                ORDER BY id
                """,
                (normalized_name, birth_date),
            ).fetchall()
        )


def issue_token(database_path: str, user_id: int, token: str) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO user_tokens (token_hash, user_id, created_at)
            VALUES (?, ?, ?)
            """,
            (
                hash_credential(token),
                user_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def record_visit(database_path: str, user_id: int, visit_date: str) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE users SET visit_count = visit_count + 1, last_visit_date = ?
            WHERE id = ?
            """,
            (visit_date, user_id),
        )


def has_seen_birthday(
    database_path: str, user_id: int, greeting_date: str
) -> bool:
    with connect(database_path) as connection:
        return (
            connection.execute(
                """
                SELECT 1 FROM birthday_greetings
                WHERE user_id = ? AND greeting_date = ?
                """,
                (user_id, greeting_date),
            ).fetchone()
            is not None
        )


def mark_birthday_seen(
    database_path: str, user_id: int, greeting_date: str
) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO birthday_greetings (user_id, greeting_date)
            VALUES (?, ?)
            """,
            (user_id, greeting_date),
        )


def discovered_egg_ids(database_path: str, user_id: int) -> set[str]:
    with connect(database_path) as connection:
        rows = connection.execute(
            "SELECT egg_id FROM discovered_eggs WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {str(row["egg_id"]) for row in rows}


def record_egg_discovery(
    database_path: str, user_id: int, egg_id: str
) -> bool:
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO discovered_eggs (user_id, egg_id, discovered_at)
            VALUES (?, ?, ?)
            """,
            (user_id, egg_id, datetime.now(timezone.utc).isoformat()),
        )
        return cursor.rowcount == 1


def submit_special_question(
    database_path: str,
    user_id: int,
    question: str,
    normalized_question: str,
) -> int:
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO special_question_reviews (
                user_id, question, normalized_question, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                question,
                normalized_question,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return int(cursor.lastrowid)


def approved_special_answer(
    database_path: str, normalized_question: str
) -> str | None:
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT answer FROM special_question_reviews
            WHERE normalized_question = ? AND status = 'approved'
            """,
            (normalized_question,),
        ).fetchone()
    return str(row["answer"]) if row and row["answer"] else None


def get_special_question_review(
    database_path: str, request_id: int, user_id: int
) -> sqlite3.Row | None:
    with connect(database_path) as connection:
        return connection.execute(
            """
            SELECT id, question, status, review_note, created_at, reviewed_at
            FROM special_question_reviews
            WHERE id = ? AND user_id = ?
            """,
            (request_id, user_id),
        ).fetchone()


def list_special_question_reviews(
    database_path: str, status: str
) -> list[sqlite3.Row]:
    with connect(database_path) as connection:
        return list(
            connection.execute(
                """
                SELECT id, user_id, question, answer, status, review_note,
                       created_at, reviewed_at
                FROM special_question_reviews
                WHERE status = ?
                ORDER BY created_at, id
                """,
                (status,),
            ).fetchall()
        )


def review_special_question(
    database_path: str,
    request_id: int,
    status: str,
    answer: str | None,
    review_note: str | None,
) -> bool:
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE special_question_reviews
            SET status = ?, answer = ?, review_note = ?, reviewed_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (
                status,
                answer,
                review_note,
                datetime.now(timezone.utc).isoformat(),
                request_id,
            ),
        )
        return cursor.rowcount == 1


def public_user(user: sqlite3.Row) -> dict[str, Any]:
    """只返回本人界面所需信息，不包含生日或凭证摘要。"""
    return {
        "id": int(user["id"]),
        "name": str(user["name"]),
        "visit_count": int(user["visit_count"]),
    }
