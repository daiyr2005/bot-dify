import asyncio
import os
from collections import defaultdict, deque

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ.get("TOKEN_BOT")
DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
DIFY_API_URL = (os.environ.get("DIFY_API_URL") or "").rstrip("/")

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)

conversations: dict[str, str] = {}
history: dict[str, deque] = defaultdict(lambda: deque(maxlen=6))
stats: dict[str, int] = defaultdict(int)

HELP_TEXT = (
    "Список команд:\n\n"
    "/start — приветствие и сброс диалога\n"
    "/help — список команд\n"
    "/new — начать новый диалог\n"
    "/history — последние 6 сообщений\n"
    "/stats — статистика вопросов\n\n"
    "Просто напиши вопрос текстом — я отвечу с помощью базы знаний о курсах."
)

START_TEXT = (
    "👋 Привет, {name}!\n\n"
    "Я бот-помощник по курсам 🎓\n"
    "Отвечу на вопросы про курсы, расписание, преподавателей и цены — "
    "на основе базы знаний.\n\n"
    "Например: «Сколько длится курс Python Start?»\n"
    "Просто напиши свой вопрос!"
)

ENROLL_TEXT = (
    "Отлично! Оставьте заявку, и мы свяжемся с вами.\n\n"
    "Напишите своё имя и номер телефона одним сообщением."
)


# ---------- Клавиатуры ----------

def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Новый диалог")],
            [KeyboardButton(text="История")],
            [KeyboardButton(text="Статистика")],
        ],
        resize_keyboard=True,
    )


def answer_keyboard() -> InlineKeyboardMarkup:
    """Кнопки под ответом бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Записаться", callback_data="enroll")],
            [InlineKeyboardButton(text="📚 все курсы", callback_data="all_courses")],
        ]
    )


def get_display_name(message: Message) -> str:
    user = message.from_user
    if user.username:
        return f"@{user.username}"
    return user.first_name or "друг"


def get_user_key(user_id: int) -> str:
    return f"telegram:{user_id}"


async def ask_dify(user_key: str, question: str) -> str:
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {},
        "query": question,
        "response_mode": "blocking",
        "conversation_id": conversations.get(user_key, ""),
        "user": user_key,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{DIFY_API_URL}/chat-messages",
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        print("Dify URL:", e.request.url)
        print("Dify response:", e.response.text)
        return f"Ошибка Dify API: {e.response.status_code}. Попробуйте позже."
    except Exception as e:
        return f"Не удалось получить ответ: {e}"

    new_conv_id = data.get("conversation_id")
    if new_conv_id:
        conversations[user_key] = new_conv_id

    return data.get("answer", "Извините, не получилось сформировать ответ.")


@router.message(CommandStart())
async def start_handler(message: Message):
    conversations.pop(get_user_key(message.from_user.id), None)
    await message.answer(
        START_TEXT.format(name=get_display_name(message)),
        reply_markup=main_keyboard(),
    )


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(HELP_TEXT)


@router.message(Command("new"))
@router.message(F.text.lower() == "новый диалог")
async def new_handler(message: Message):
    conversations.pop(get_user_key(message.from_user.id), None)
    await message.answer("Следующее сообщение начнёт новый диалог.")


@router.message(Command("history"))
@router.message(F.text.lower() == "история")
async def history_handler(message: Message):
    msgs = history[get_user_key(message.from_user.id)]
    if not msgs:
        await message.answer("История пуста.")
        return
    text = "История последних сообщений:\n\n" + "\n".join(
        f"{i + 1}. {m}" for i, m in enumerate(msgs)
    )
    await message.answer(text)


@router.message(Command("stats"))
@router.message(F.text.lower() == "статистика")
async def stats_handler(message: Message):
    count = stats[get_user_key(message.from_user.id)]
    await message.answer(f"Статистика:\n\nВсего отправлено вопросов: {count}")



@router.callback_query(F.data == "enroll")
async def enroll_handler(callback: CallbackQuery):
    await callback.answer()  # убирает «часики» на кнопке
    await callback.message.answer(ENROLL_TEXT)


@router.callback_query(F.data == "all_courses")
async def all_courses_handler(callback: CallbackQuery):
    await callback.answer()
    user_key = get_user_key(callback.from_user.id)
    stats[user_key] += 1

    await callback.bot.send_chat_action(callback.message.chat.id, ChatAction.TYPING)
    answer = await ask_dify(user_key, "Расскажи  все из базаданых курсы")
    await callback.message.answer(answer, reply_markup=answer_keyboard())


@router.message(F.text)
async def question_handler(message: Message):
    user_key = get_user_key(message.from_user.id)
    history[user_key].append(message.text)
    stats[user_key] += 1

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    answer = await ask_dify(user_key, message.text)
    await message.answer(answer, reply_markup=answer_keyboard())


async def main():
    if not TELEGRAM_BOT_TOKEN or not DIFY_API_KEY or not DIFY_API_URL:
        raise SystemExit("Задайте TOKEN_BOT, DIFY_API_KEY и DIFY_API_URL в .env.")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)

    dp = Dispatcher()
    dp.include_router(router)

    print("Бот запущен, ожидаю сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())