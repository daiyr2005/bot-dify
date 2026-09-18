
import asyncio
import os
import time
from collections import defaultdict, deque
from dotenv import  load_dotenv
import httpx
load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ.get("TOKEN_BOT")
DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
DIFY_API_URL = os.environ.get("DIFY_API_URL")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

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
    "👋 Привет!\n\n"
    "Я бот-помощник по курсам 🎓\n"
    "Отвечу на вопросы про курсы, расписание, преподавателей и цены — "
    "на основе базы знаний.\n\n"
    "Например: «Сколько длится курс Python Start?»\n"
    "Просто напиши свой вопрос!"
)


async def send_message(client: httpx.AsyncClient, chat_id: int, text: str, reply_markup: dict | None = None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)


def main_keyboard() -> dict:
    return {
        "keyboard": [
            [{"text": "Новый диалог"}],
            [{"text": "История"}],
            [{"text": "Статистика"}],
        ],
        "resize_keyboard": True,
    }


async def ask_dify(client: httpx.AsyncClient, user_key: str, question: str) -> str:

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
        resp = await client.post(
            f"{DIFY_API_URL}/chat-messages",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return f"Ошибка Dify API: {e.response.status_code}. Попробуйте позже."
    except Exception as e:
        return f"Не удалось получить ответ: {e}"

    # Сохраняем conversation_id для продолжения диалога с контекстом
    new_conv_id = data.get("conversation_id")
    if new_conv_id:
        conversations[user_key] = new_conv_id

    answer = data.get("answer", "Извините, не получилось сформировать ответ.")
    return answer


async def handle_command(client: httpx.AsyncClient, chat_id: int, user_key: str, command: str):
    if command in ("/start", "новый диалог", "/new"):
        conversations.pop(user_key, None)
        if command == "/start":
            await send_message(client, chat_id, START_TEXT, main_keyboard())
        else:
            await send_message(client, chat_id, "Следующее сообщение начнёт новый диалог.")
    elif command in ("/help",):
        await send_message(client, chat_id, HELP_TEXT)
    elif command in ("/history", "история"):
        msgs = history[user_key]
        if not msgs:
            await send_message(client, chat_id, "История пуста.")
        else:
            text = "История последних сообщений:\n\n" + "\n".join(
                f"{i+1}. {m}" for i, m in enumerate(msgs)
            )
            await send_message(client, chat_id, text)
    elif command in ("/stats", "статистика"):
        count = stats[user_key]
        await send_message(client, chat_id, f"Статистика:\n\nВсего отправлено вопросов: {count}")
    else:
        return False
    return True


async def main():
    if not TELEGRAM_BOT_TOKEN or not DIFY_API_KEY:
        raise SystemExit("Задайте TELEGRAM_BOT_TOKEN и DIFY_API_KEY в переменных окружения.")

    offset = 0
    async with httpx.AsyncClient() as client:
        print("Бот запущен, ожидаю сообщения...")
        while True:
            try:
                resp = await client.get(
                    f"{TELEGRAM_API}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                    timeout=40,
                )
                data = resp.json()
            except Exception as e:
                print(f"Ошибка получения обновлений: {e}")
                await asyncio.sleep(3)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat = message.get("chat", {})
                text = message.get("text")
                sender_id = message.get("from", {}).get("id")

                if chat.get("type") != "private" or not text or sender_id is None:
                    continue

                user_key = f"telegram:{sender_id}"
                chat_id = chat["id"]
                text_lower = text.strip().lower()

                handled = await handle_command(client, chat_id, user_key, text_lower)
                if handled:
                    continue

                # Обычный вопрос — уходит в Dify
                history[user_key].append(text)
                stats[user_key] += 1

                await client.post(
                    f"{TELEGRAM_API}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"},
                )

                answer = await ask_dify(client, user_key, text)
                await send_message(client, chat_id, answer, main_keyboard())


if __name__ == "__main__":
    asyncio.run(main())