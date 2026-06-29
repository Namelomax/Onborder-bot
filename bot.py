"""Подсистема «Telegram-интерфейс» (ТЗ 4.1.1).

Точка входа в приложение. Реализует:
  - приём текстовых сообщений и команд от пользователей;
  - отправку ответов, уведомлений и учебных материалов;
  - интерактивное меню с кнопками навигации по разделам онбординга.

Связывает между собой подсистемы: ИИ-ассистент, База знаний, Хранение данных.
Реализован на библиотеке aiogram (Telegram Bot API). Для запуска нужен только
токен бота от @BotFather — api_id/api_hash не требуются.

Запуск:  python bot.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import ai_agent
import config
import database as db
import knowledge_base as kb
import onboarding
import tests_data

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("onboarding-bot")

dp = Dispatcher()

# Состояние активных сессий тестирования в памяти: {user_id: {test_id, q, score}}
test_sessions: dict[int, dict] = {}
# Пользователи, от которых ожидается свободный вопрос к ИИ
awaiting_question: set[int] = set()


# --- Клавиатуры -------------------------------------------------------------

def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """rows: список рядов, каждый ряд — список (текст, callback_data)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
        for row in rows
    ])


def main_menu() -> InlineKeyboardMarkup:
    return _kb([
        [("📚 База знаний", "menu:kb"), ("🎯 Онбординг", "menu:onb")],
        [("📝 Тестирование", "menu:test"), ("📊 Мой прогресс", "menu:progress")],
        [("❓ Задать вопрос ИИ", "menu:ask")],
    ])


def back_menu() -> InlineKeyboardMarkup:
    return _kb([[("⬅️ В главное меню", "menu:main")]])


async def safe_edit(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup):
    """Редактирует сообщение, игнорируя ошибку «message is not modified»."""
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc):
            raise


# --- Команды ----------------------------------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: Message):
    name = message.from_user.first_name or "тренер"
    db.register_user(message.from_user.id, name)
    awaiting_question.discard(message.from_user.id)
    text = (
        f"👋 Здравствуйте, {name}!\n\n"
        "Я — ИИ-ассистент онбординга тренеров Байкальского центра спортивного "
        "программирования.\n\n"
        "Я помогу вам пройти адаптацию: выдам учебные материалы, проведу по этапам "
        "онбординга, проверю знания тестом и отвечу на вопросы.\n\n"
        "Выберите раздел или просто напишите свой вопрос 👇"
    )
    await message.answer(text, reply_markup=main_menu())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Доступные команды:\n"
        "/start — главное меню\n"
        "/help — справка\n\n"
        "Можно просто написать вопрос текстом — ответит ИИ-ассистент.",
        reply_markup=main_menu(),
    )


# --- Обработчик меню (callback-кнопки) --------------------------------------

@dp.callback_query()
async def on_callback(cb: CallbackQuery):
    data = cb.data
    user_id = cb.from_user.id

    if data == "menu:main":
        awaiting_question.discard(user_id)
        await safe_edit(cb, "Главное меню. Выберите раздел 👇", main_menu())

    elif data == "menu:kb":
        await show_knowledge_base(cb)

    elif data.startswith("doc:"):
        await show_document(cb, data[len("doc:"):])

    elif data == "menu:onb":
        await show_onboarding(cb)

    elif data.startswith("stage:"):
        await show_stage(cb, int(data[len("stage:"):]))

    elif data.startswith("chk:"):
        _, stage_id, item_key = data.split(":", 2)
        db.toggle_checklist_item(user_id, item_key)
        db.set_stage(user_id, int(stage_id))
        await show_stage(cb, int(stage_id))

    elif data == "menu:test":
        await start_test(cb, "onboarding_basic")

    elif data.startswith("ans:"):
        await handle_answer(cb, data)

    elif data == "menu:progress":
        await show_progress(cb)

    elif data == "menu:ask":
        awaiting_question.add(user_id)
        await safe_edit(
            cb,
            "✍️ Напишите ваш вопрос одним сообщением — я найду ответ в базе знаний.",
            back_menu(),
        )
    else:
        await cb.answer("Неизвестная команда")
        return
    await cb.answer()


# --- База знаний ------------------------------------------------------------

async def show_knowledge_base(cb: CallbackQuery):
    docs = kb.list_documents()
    if not docs:
        await safe_edit(cb, "База знаний пуста.", back_menu())
        return
    rows = [[(f"📄 {d['title']}", f"doc:{d['key']}")] for d in docs]
    rows.append([("⬅️ В главное меню", "menu:main")])
    await safe_edit(cb, "📚 База знаний. Выберите материал:", _kb(rows))


async def show_document(cb: CallbackQuery, key: str):
    text = kb.get_document(key)
    if text is None:
        await cb.answer("Документ не найден", show_alert=True)
        return
    if len(text) > 3800:
        text = text[:3800] + "\n\n… (материал сокращён)"
    await safe_edit(cb, text, _kb([[("⬅️ К базе знаний", "menu:kb")]]))


# --- Онбординг и чек-листы ---------------------------------------------------

async def show_onboarding(cb: CallbackQuery):
    progress = db.get_progress(cb.from_user.id)
    checklist = progress["checklist"]
    rows = []
    for stage in onboarding.STAGES:
        done = sum(1 for key, _ in stage["checklist"] if checklist.get(key))
        total = len(stage["checklist"])
        mark = "✅" if done == total else f"{done}/{total}"
        rows.append([(f"{mark} {stage['title']}", f"stage:{stage['id']}")])
    rows.append([("⬅️ В главное меню", "menu:main")])
    await safe_edit(
        cb,
        "🎯 Этапы онбординга.\nВыберите этап, чтобы открыть материал и чек-лист:",
        _kb(rows),
    )


async def show_stage(cb: CallbackQuery, stage_id: int):
    stage = onboarding.get_stage(stage_id)
    if stage is None:
        await cb.answer("Этап не найден", show_alert=True)
        return
    progress = db.get_progress(cb.from_user.id)
    checklist = progress["checklist"]

    text = (
        f"🎯 Этап {stage_id + 1}/{onboarding.total_stages()}: {stage['title']}\n\n"
        "Чек-лист (нажмите, чтобы отметить):"
    )
    rows = []
    for key, label in stage["checklist"]:
        mark = "☑️" if checklist.get(key, False) else "⬜"
        rows.append([(f"{mark} {label}", f"chk:{stage_id}:{key}")])
    rows.append([("📄 Открыть материал этапа", f"doc:{stage['doc']}")])
    rows.append([("⬅️ К этапам", "menu:onb")])
    await safe_edit(cb, text, _kb(rows))


# --- Тестирование -----------------------------------------------------------

async def start_test(cb: CallbackQuery, test_id: str):
    test = tests_data.get_test(test_id)
    if test is None:
        await cb.answer("Тест не найден", show_alert=True)
        return
    test_sessions[cb.from_user.id] = {"test_id": test_id, "q": 0, "score": 0}
    await send_question(cb)


async def send_question(cb: CallbackQuery):
    session = test_sessions.get(cb.from_user.id)
    test = tests_data.get_test(session["test_id"])
    q_index = session["q"]
    question = test["questions"][q_index]

    rows = [
        [(opt, f"ans:{session['test_id']}:{q_index}:{i}")]
        for i, opt in enumerate(question["options"])
    ]
    text = (
        f"📝 {test['title']}\n"
        f"Вопрос {q_index + 1} из {len(test['questions'])}\n\n"
        f"{question['text']}"
    )
    await safe_edit(cb, text, _kb(rows))


async def handle_answer(cb: CallbackQuery, data: str):
    _, test_id, q_index, opt = data.split(":")
    q_index, opt = int(q_index), int(opt)
    session = test_sessions.get(cb.from_user.id)
    if not session or session["test_id"] != test_id or session["q"] != q_index:
        await cb.answer("Сессия теста устарела. Начните заново.", show_alert=True)
        return

    test = tests_data.get_test(test_id)
    question = test["questions"][q_index]
    if opt == question["answer"]:
        session["score"] += 1
        await cb.answer("✅ Верно!")
    else:
        correct = question["options"][question["answer"]]
        await cb.answer(f"❌ Неверно. Правильный ответ: {correct}", show_alert=True)

    session["q"] += 1
    if session["q"] < len(test["questions"]):
        await send_question(cb)
    else:
        await finish_test(cb, session)


async def finish_test(cb: CallbackQuery, session: dict):
    test = tests_data.get_test(session["test_id"])
    score, total = session["score"], len(test["questions"])
    db.save_test_result(cb.from_user.id, session["test_id"], score, total)
    test_sessions.pop(cb.from_user.id, None)

    passed = score >= (total // 2 + 1)
    verdict = "🎉 Тест пройден!" if passed else "📚 Стоит повторить материал."
    await safe_edit(
        cb,
        f"📝 {test['title']} завершён.\n\nРезультат: {score} из {total}\n{verdict}",
        _kb([[("🔁 Пройти заново", "menu:test")], [("⬅️ В главное меню", "menu:main")]]),
    )


# --- Прогресс ---------------------------------------------------------------

async def show_progress(cb: CallbackQuery):
    progress = db.get_progress(cb.from_user.id)
    checklist = progress["checklist"]
    lines = ["📊 Ваш прогресс онбординга:\n"]
    for stage in onboarding.STAGES:
        done = sum(1 for key, _ in stage["checklist"] if checklist.get(key))
        total = len(stage["checklist"])
        mark = "✅" if done == total else "🔸"
        lines.append(f"{mark} {stage['title']}: {done}/{total}")

    results = db.get_test_results(cb.from_user.id)
    if results:
        last = results[0]
        lines.append(f"\n📝 Последний тест: {last['score']}/{last['total']}")
    else:
        lines.append("\n📝 Тест ещё не пройден.")

    await safe_edit(cb, "\n".join(lines), back_menu())


# --- Свободные вопросы к ИИ-ассистенту --------------------------------------

@dp.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message):
    user_id = message.from_user.id
    question = (message.text or "").strip()
    if not question:
        return

    db.register_user(user_id, message.from_user.first_name or "тренер")
    awaiting_question.discard(user_id)
    db.save_message(user_id, "user", question)

    await message.bot.send_chat_action(message.chat.id, "typing")
    history = db.get_history(user_id, limit=6)
    try:
        answer = await ai_agent.ask(question, history=history[:-1])
    except ai_agent.AIAssistantUnavailable as exc:
        logger.warning("ИИ-ассистент недоступен: %s", exc)
        await message.answer(
            "⚠️ ИИ-ассистент временно недоступен. Попробуйте позже или "
            "воспользуйтесь разделами меню (/start).",
        )
        return

    db.save_message(user_id, "assistant", answer)
    await message.answer(answer, reply_markup=back_menu())


# --- Запуск -----------------------------------------------------------------

async def main():
    db.init_db()
    logger.info("Инициализация БД завершена. Запуск бота…")

    # Прокси (если Telegram заблокирован) подключается через сессию aiohttp
    session = AiohttpSession(proxy=config.TELEGRAM_PROXY) if config.TELEGRAM_PROXY else None
    bot = Bot(token=config.BOT_TOKEN, session=session)

    logger.info("Бот запущен. Ожидание сообщений.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
