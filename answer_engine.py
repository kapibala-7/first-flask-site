"""答案匹配与彩蛋优先级：生日 > 精确问题 > 彩蛋 > 普通关键词。"""

from __future__ import annotations

import random
import re
from typing import Any

from answer_data import ANSWER_CATEGORIES, EASTER_EGGS, SPECIAL_QUESTIONS

BIRTHDAY_ANSWER = "生日快乐。愿新的一岁有温柔相伴，也有勇气走向你想去的地方。"


def normalize_question(question: str) -> str:
    normalized = re.sub(r"\s+", "", question).casefold()
    return normalized.strip("？?。！!，,；;：:")


def find_category(question: str) -> str:
    """按关键词命中数量选择类别；同分时保持答案数据中的稳定顺序。"""
    normalized = normalize_question(question)
    best_category = "一般指引"
    best_score = 0

    for category, data in ANSWER_CATEGORIES.items():
        score = sum(
            1
            for keyword in data["keywords"]
            if normalize_question(keyword) in normalized
        )
        if score > best_score:
            best_category = category
            best_score = score
    return best_category


def _make_egg_result(egg: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": egg["answer"],
        "category": egg["name"],
        "is_easter_egg": True,
        "egg_id": egg["id"],
        "egg_tier": egg["tier"],
        "effect": egg["effect"],
        "sound": egg["sound"],
        "save_discovery": egg["save_discovery"],
    }


def resolve_answer(
    question: str,
    *,
    birthday_pending: bool = False,
    visit_count: int = 0,
    discovered_eggs: set[str] | None = None,
    approved_special_questions: dict[str, str] | None = None,
    rng: Any = random,
) -> dict[str, Any]:
    """根据明确顺序匹配祝福、精确答案、彩蛋和普通答案。"""
    discovered = discovered_eggs or set()

    if birthday_pending:
        return {
            "answer": BIRTHDAY_ANSWER,
            "category": "生日祝福",
            "is_easter_egg": False,
            "priority": "birthday",
            "effect": "birthday",
            "sound": "birthday",
        }

    normalized = normalize_question(question)
    special = SPECIAL_QUESTIONS.get(normalized)
    if special:
        return {
            "answer": special["answer"],
            "category": special["category"],
            "is_easter_egg": False,
            "priority": "exact",
            "effect": "page-whisper",
            "sound": "answer",
        }
    approved_answer = (approved_special_questions or {}).get(normalized)
    if approved_answer:
        return {
            "answer": approved_answer,
            "category": "指定问题",
            "is_easter_egg": False,
            "priority": "approved-special",
            "effect": "page-whisper",
            "sound": "answer",
        }

    for egg in sorted(EASTER_EGGS, key=lambda item: item["priority"], reverse=True):
        if egg["id"] in discovered and not egg["repeatable"]:
            continue

        trigger = egg["trigger"]
        if trigger == "hidden":
            phrases = {normalize_question(phrase) for phrase in egg["phrases"]}
            matched = normalized in phrases
        elif trigger == "combination":
            keyword_groups = egg.get("keyword_groups")
            if keyword_groups:
                matched = all(
                    any(normalize_question(word) in normalized for word in group)
                    for group in keyword_groups
                )
            else:
                matched = all(
                    normalize_question(word) in normalized
                    for word in egg["keywords"]
                )
        elif trigger == "keyword":
            matched = any(
                normalize_question(word) in normalized for word in egg["keywords"]
            )
        elif trigger == "visit_count":
            matched = visit_count >= egg["minimum_visits"]
        elif trigger == "probability":
            matched = egg["id"] not in discovered and rng.random() < egg["chance"]
        else:
            matched = False

        if matched:
            return _make_egg_result(egg)

    category = find_category(question)
    return {
        "answer": rng.choice(ANSWER_CATEGORIES[category]["answers"]),
        "category": category,
        "is_easter_egg": False,
        "effect": "answer",
        "sound": "answer",
    }
