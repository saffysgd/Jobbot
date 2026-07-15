import asyncio
import logging
import json
import os
from typing import Optional, Dict, Any

from maxapi import Bot, Dispatcher, F
from maxapi.types import (
    MessageCreated,
    MessageCallback,
    Command,
    BotStarted,
    Callback,
    Message,
    CallbackButton,
    ButtonsPayload,
    Attachment,
    LinkButton,
)
from maxapi.enums.intent import Intent

# ==================== КОНФИГУРАЦИЯ ====================
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
GROUP_ID = int(os.environ.get("GROUP_ID", "0"))
TOKEN = os.environ.get("MAX_BOT_TOKEN", "")

if not TOKEN:
    raise ValueError("MAX_BOT_TOKEN не задан!")
if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID не задан!")
if GROUP_ID == 0:
    raise ValueError("GROUP_ID не задан!")

if GROUP_ID > 0:
    GROUP_ID = -GROUP_ID

jobs_db: Dict[str, Any] = {}

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=TOKEN)
dp = Dispatcher()

ADMIN_LINK = "https://max.ru/u/f9LHodD0cOIB8sUjpYRTavPmwPuBLj6X8zHuBbXFJV24iA1JjfegPd9PzDE"

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def build_job_keyboard() -> list:
    """Все кнопки — LinkButton, ведут в диалог с админом."""
    buttons = [
        [
            LinkButton(text="🙋 Беру", url=ADMIN_LINK),
            LinkButton(text="👥 Беру вдвоём", url=ADMIN_LINK),
        ],
        [
            LinkButton(text="❓ Задать вопрос", url=ADMIN_LINK),
        ]
    ]
    payload = ButtonsPayload(buttons=buttons)
    return [Attachment(type="inline_keyboard", payload=payload)]


def build_admin_keyboard(job_msg_id: str) -> list:
    btn = CallbackButton(
        text="🔒 Закрыть заявку",
        payload=json.dumps({"action": "close", "job_msg_id": job_msg_id}),
        intent=Intent.NEGATIVE
    )
    payload = ButtonsPayload(buttons=[[btn]])
    return [Attachment(type="inline_keyboard", payload=payload)]


def build_group_message(job_text: str, status: str) -> str:
    """Статус в конце текста."""
    if status == "active":
        return f"{job_text}\n\nСтатус: Заявка актуальна ✅"
    elif status == "closed":
        return f"{job_text}\n\nСтатус: Заявка закрыта ❌"
    return job_text


# ==================== ОБРАБОТЧИКИ ====================

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="👋 Бот для заявок. Админ пишет текст — я публикую в группу."
    )


@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    user_id = event.message.sender.user_id if event.message.sender else None
    if user_id == ADMIN_ID:
        await event.message.answer("👨‍💼 Отправь текст заявки — опубликую в группе.")
    else:
        await event.message.answer("🤖 Бот для заявок.")


@dp.message_created()
async def handle_admin_message(event: MessageCreated):
    """Админ пишет текст — бот дублирует в группу и админу."""
    if event.message.sender is None:
        return

    user_id = event.message.sender.user_id
    chat_id = event.message.recipient.chat_id
    job_text = event.message.body.text if event.message.body else None

    if user_id != ADMIN_ID:
        return
    if chat_id == GROUP_ID:
        await event.message.answer("❌ Пиши мне в личку, не в группу!")
        return
    if not job_text:
        await event.message.answer("❌ Отправь текстовое сообщение.")
        return

    try:
        # Публикуем в группу
        group_text = build_group_message(job_text, "active")
        attachments = build_job_keyboard()

        response = await bot.send_message(
            chat_id=GROUP_ID,
            text=group_text,
            attachments=attachments
        )

        group_message_id = str(response.message.body.mid) if response.message and response.message.body else None

        if group_message_id:
            jobs_db[group_message_id] = {
                "status": "active",
                "text": job_text,
            }

            # Дублируем админу с кнопкой закрыть
            admin_attachments = build_admin_keyboard(group_message_id)
            admin_response = await bot.send_message(
                user_id=ADMIN_ID,
                text=group_text,
                attachments=admin_attachments
            )

            admin_msg_id = str(admin_response.message.body.mid) if admin_response.message and admin_response.message.body else None
            jobs_db[group_message_id]["admin_msg_id"] = admin_msg_id

            await event.message.answer(f"✅ Опубликовано! ID: {group_message_id}")
            logger.info(f"Job published: {group_message_id}")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        await event.message.answer(f"❌ Ошибка: {e}")


# ==================== CALLBACK'И ====================

@dp.message_callback()
async def handle_callback(event: MessageCallback):
    callback: Callback = event.callback
    data = json.loads(callback.payload) if callback.payload else {}
    user_id = callback.user.user_id

    action = data.get("action")
    job_msg_id = data.get("job_msg_id")

    message: Optional[Message] = event.message
    if not message or not message.body:
        await event.answer(notification="❌ Ошибка")
        return

    # === ЗАКРЫТИЕ ===
    if action == "close":
        if user_id != ADMIN_ID:
            await event.answer(notification="❌ Только админ")
            return

        if not job_msg_id:
            await event.answer(notification="❌ Ошибка")
            return

        job_msg_id_str = str(job_msg_id)
        job_to_close = jobs_db.get(job_msg_id_str)

        if not job_to_close:
            await event.answer(notification="❌ Заявка не найдена")
            return

        job_to_close["status"] = "closed"

        try:
            # Закрываем в группе — статус в конце
            closed_text = build_group_message(job_to_close["text"], "closed")
            await bot.edit_message(message_id=job_msg_id, text=closed_text)

            # Удаляем кнопку у админа
            text = job_to_close['text'][:100]
            if len(job_to_close['text']) > 100:
                text += "..."

            await message.edit(
                text=f"{text}\n\nСтатус: Заявка закрыта ❌",
                attachments=[]
            )

            await event.answer(notification="✅ Закрыта!")
            logger.info(f"Closed: {job_msg_id}")

        except Exception as e:
            logger.error(f"Close error: {e}")
            await event.answer(notification="❌ Ошибка закрытия")

    else:
        await event.answer(notification="❌ Неизвестное действие")


# ==================== ЗАПУСК ====================

async def main():
    logger.info(f"ADMIN_ID={ADMIN_ID}, GROUP_ID={GROUP_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
