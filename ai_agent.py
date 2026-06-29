"""Подсистема «ИИ-ассистент» (ТЗ 4.1.1).

Реализует смысловую обработку запросов пользователя на естественном языке,
поиск релевантной информации в базе знаний и формирование развёрнутого ответа
с учётом контекста сессии.

Архитектурно реализован как агент: модель получает системную инструкцию о роли,
найденный в базе знаний контекст (RAG) и историю диалога, после чего формирует
ответ. В качестве LLM используется OpenRouter (модель openrouter/owl-alpha).
Роль соответствует подсистеме «ИИ-ассистент» из ТЗ.

При недоступности ИИ-ассистента бот информирует пользователя (ТЗ 4.2).
"""
import httpx

import config
import knowledge_base

SYSTEM_PROMPT = (
    "Ты — ИИ-ассистент онбординга тренеров Байкальского центра спортивного "
    "программирования. Помогаешь новым тренерам адаптироваться: отвечаешь на "
    "вопросы, опираясь на материалы базы знаний организации.\n"
    "Правила:\n"
    "- Отвечай на русском языке, вежливо и по делу.\n"
    "- Используй информацию из предоставленного контекста базы знаний. Если в "
    "контексте нет ответа, честно скажи об этом и предложи обратиться к "
    "администратору центра.\n"
    "- Не выдумывай факты, которых нет в базе знаний.\n"
    "- Отвечай кратко и структурированно."
)


class AIAssistantUnavailable(Exception):
    """ИИ-ассистент недоступен (сеть, таймаут, ошибка API)."""


async def ask(user_question: str, history: list[dict] | None = None) -> str:
    """Задать вопрос ИИ-ассистенту.

    :param user_question: вопрос пользователя на естественном языке.
    :param history: последние реплики диалога [{"role", "content"}].
    :raises AIAssistantUnavailable: при сетевой ошибке/таймауте/ошибке API.
    """
    context = knowledge_base.build_context(user_question)
    context_block = (
        f"Контекст из базы знаний:\n{context}" if context
        else "Контекст из базы знаний: (релевантных материалов не найдено)"
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({
        "role": "user",
        "content": f"{context_block}\n\nВопрос пользователя: {user_question}",
    })

    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # Необязательные заголовки атрибуции OpenRouter
        "HTTP-Referer": "https://github.com/",
        "X-Title": "AI Onboarding Bot",
    }

    try:
        async with httpx.AsyncClient(timeout=config.AI_TIMEOUT_SECONDS) as client:
            resp = await client.post(config.OPENROUTER_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise AIAssistantUnavailable(str(exc)) from exc
