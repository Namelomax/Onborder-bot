"""Подсистема «База знаний» (ТЗ 4.1.1).

Учебные материалы хранятся в формате Markdown в папке knowledge_base/.
Модуль обеспечивает:
  - загрузку документов;
  - поиск релевантных материалов по запросу (упрощённый лексический поиск);
  - обновление содержимого без остановки системы (файлы читаются при каждом
    обращении, поэтому правка .md в репозитории сразу доступна боту — ТЗ 4.9).
"""
import os
import re
from typing import Optional

import config


def _kb_dir() -> str:
    return config.KNOWLEDGE_BASE_DIR


def list_documents() -> list[dict]:
    """Список документов базы знаний: ключ (имя файла) и заголовок."""
    docs = []
    directory = _kb_dir()
    if not os.path.isdir(directory):
        return docs
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".md"):
            continue
        title = _extract_title(os.path.join(directory, filename))
        docs.append({"key": filename, "title": title})
    return docs


def _extract_title(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#"):
                    return line.lstrip("#").strip()
    except OSError:
        pass
    return os.path.basename(path)


def get_document(key: str) -> Optional[str]:
    """Полный текст документа по ключу (имени файла)."""
    path = os.path.join(_kb_dir(), key)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def search(query: str, max_docs: int = 3) -> list[dict]:
    """Лексический поиск релевантных документов.

    Возвращает список словарей {key, title, text, score}, отсортированный по
    убыванию релевантности. Используется ИИ-агентом для формирования контекста
    (Retrieval-Augmented Generation).
    """
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    results = []
    for doc in list_documents():
        text = get_document(doc["key"]) or ""
        doc_tokens = _tokenize(text)
        if not doc_tokens:
            continue
        doc_token_set = set(doc_tokens)
        # Пересечение терминов запроса и документа + частотный вес
        overlap = query_tokens & doc_token_set
        if not overlap:
            continue
        score = sum(doc_tokens.count(t) for t in overlap)
        results.append({
            "key": doc["key"],
            "title": doc["title"],
            "text": text,
            "score": score,
        })

    results.sort(key=lambda d: d["score"], reverse=True)
    return results[:max_docs]


def build_context(query: str, max_chars: int = 4000) -> str:
    """Формирует текстовый контекст из релевантных документов для ИИ-агента."""
    chunks = []
    used = 0
    for doc in search(query):
        block = f"### {doc['title']}\n{doc['text']}\n"
        if used + len(block) > max_chars:
            block = block[: max_chars - used]
        chunks.append(block)
        used += len(block)
        if used >= max_chars:
            break
    return "\n".join(chunks)
