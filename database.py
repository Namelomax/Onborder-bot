"""Подсистема «Хранение данных» (ТЗ 4.1.1).

В качестве СУБД для учебного демонстрационного варианта используется SQLite —
лёгкая встраиваемая БД, не требующая отдельного сервера. Хранит:
  - данные пользователей;
  - историю диалогов;
  - результаты тестирования;
  - прогресс прохождения этапов онбординга.

Критические операции выполняются с подтверждением записи (commit) — ТЗ 4.2.
"""
import json
import sqlite3
import time
from typing import Optional

import config


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создаёт таблицы при первом запуске."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                name        TEXT,
                created_at  REAL
            );

            CREATE TABLE IF NOT EXISTS dialogs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                role      TEXT,
                content   TEXT,
                ts        REAL
            );

            CREATE TABLE IF NOT EXISTS test_results (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER,
                test_id  TEXT,
                score    INTEGER,
                total    INTEGER,
                ts       REAL
            );

            CREATE TABLE IF NOT EXISTS progress (
                user_id        INTEGER PRIMARY KEY,
                current_stage  INTEGER DEFAULT 0,
                checklist      TEXT DEFAULT '{}'
            );
            """
        )
        conn.commit()


# --- Пользователи -----------------------------------------------------------

def register_user(telegram_id: int, name: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id, name, created_at) VALUES (?, ?, ?)",
            (telegram_id, name, time.time()),
        )
        conn.execute(
            "INSERT OR IGNORE INTO progress (user_id) VALUES (?)",
            (telegram_id,),
        )
        conn.commit()


# --- История диалогов -------------------------------------------------------

def save_message(user_id: int, role: str, content: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO dialogs (user_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (user_id, role, content, time.time()),
        )
        conn.commit()


def get_history(user_id: int, limit: int = 10) -> list[dict]:
    """Последние сообщения диалога в хронологическом порядке."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM dialogs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# --- Результаты тестирования ------------------------------------------------

def save_test_result(user_id: int, test_id: str, score: int, total: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO test_results (user_id, test_id, score, total, ts) VALUES (?, ?, ?, ?, ?)",
            (user_id, test_id, score, total, time.time()),
        )
        conn.commit()


def get_test_results(user_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT test_id, score, total FROM test_results WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- Прогресс онбординга ----------------------------------------------------

def get_progress(user_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT current_stage, checklist FROM progress WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return {"current_stage": 0, "checklist": {}}
    return {
        "current_stage": row["current_stage"],
        "checklist": json.loads(row["checklist"] or "{}"),
    }


def set_stage(user_id: int, stage: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE progress SET current_stage = ? WHERE user_id = ?",
            (stage, user_id),
        )
        conn.commit()


def toggle_checklist_item(user_id: int, item_key: str) -> bool:
    """Переключает пункт чек-листа. Возвращает новое состояние (True=выполнен)."""
    progress = get_progress(user_id)
    checklist = progress["checklist"]
    new_state = not checklist.get(item_key, False)
    checklist[item_key] = new_state
    with _connect() as conn:
        conn.execute(
            "UPDATE progress SET checklist = ? WHERE user_id = ?",
            (json.dumps(checklist, ensure_ascii=False), user_id),
        )
        conn.commit()
    return new_state
