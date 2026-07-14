"""
Бот для управления заявками на работу через MAX API.
Адаптирован для деплоя на Amvera Cloud.
"""

import asyncio
import logging
import json
import os
from datetime import datetime
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
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_user_name(user) -> str:
    if user is None:
        return "Unknown"
    if user.username:
        return f"@{user.username}"
    name = user.first_name
    if user.last_name:
        name += f" {user.last_name}"
    return name or f"User_{user.user_id}"


def build_job_keyboard(status: str = "free") -> Optional[list]:
    if status in ("booked", "closed"):
        return None

    btn1 = CallbackButton(
        text="🙋 Беру",
        payload=json.dumps({"action": "take", "type": "single"}),
        intent=Intent.POSITIVE
    )
    btn2 = CallbackButton(
        text="👥 Беру вдвоём",
        payload=json.dumps({"action": "take", "type": "pair"}),
        intent=Intent.POSITIVE
    )
    btn3 = LinkButton(
        text="❓ Задать вопрос",
        url=f"https://max.me/{ADMIN_ID}"
    )

    payload = ButtonsPayload(buttons=[[btn1, btn2], [btn3]])
    return [Attachment(type="inline_keyboard", payload=payload)]


def build_admin_keyboard(job_msg_id: str) -> list:
    btn = CallbackButton(
        text="🔒 Закрыть заявку",
        payload=json.dumps({"action": "close", "job_msg_id": job_msg_id}),
        intent=Intent.NEGATIVE
    )
    payload = ButtonsPayload(buttons=[[btn]])
    return [Attachment(type="inline_keyboard", payload=payload)]


def build_group_message(job_text: str, status: str, user_name: Optional[str] = None,
                        take_type: Optional[str] = None, created_at: Optional[str] = None) -> str:
    time_str = created_at[:16].replace("T", " ") if created_at else datetime.now().strftime("%d.%m.%Y %H:%M")

    if status == "free":
        return (
            f"📢 НОВАЯ ЗАЯВКА\n"
            f"⏰ {time_str}\n"
            "━━━━━━━━━━━━━━\n\n"
            f"{job_text}\n\n"
            "━━━━━━━━━━━━━━\n"
            "🟢 Статус: Свободно"
        )
    elif status == "booked":
        type_label = "вдвоём" if take_type == "pair" else "один"
        return (
            f"📢 ЗАЯВКА\n"
            f"⏰ {time_str}\n"
            "━━━━━━━━━━━━━━\n\n"
            f"{job_text}\n\n"
            "━━━━━━━━━━━━━━\n"
            f"🟡 Статус: Забронировано ({type_label})\n"
            f"👤 Исполнитель: {user_name or 'Неизвестно'}"
        )
    elif status == "closed":
        return (
            f"✅ ЗАКРЫТО\n"
            f"⏰ {time_str}\n"
            "━━━━━━━━━━━━━━\n\n"
            f"{job_text}\n\n"
            "━━━━━━━━━━━━━━\n"
            "❗️ Заявка выполнена"
        )
    return job_text


# ==================== ОБРАБОТЧИКИ ====================

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    logger.info(f"BOT_STARTED: chat_id={event.chat_id}")
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="👋 Привет! Я бот для управления заявками.\n\n"
             "Администраторы могут отправлять мне тексты заявок, "
             "а я буду публиковать их в группе с кнопками для исполнителей."
    )


@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    user_id = event.message.sender.user_id if event.message.sender else None
    logger.info(f"CMD_START: user_id={user_id}, ADMIN_ID={ADMIN_ID}")

    if user_id == ADMIN_ID:
        await event.message.answer(
            "👨‍💼 Панель администратора\n\n"
            "Отправьте мне текст заявки — я опубликую её в группе."
        )
    else:
        await event.message.answer(
            "🤖 Я бот для управления заявками."
        )


@dp.message_created()
async def handle_admin_message(event: MessageCreated):
    """Обработка сообщений от администратора (новые заявки)."""
    logger.info("=" * 60)
    logger.info("ADMIN_MESSAGE RECEIVED")
    logger.info("=" * 60)

    # Проверяем sender
    if event.message.sender is None:
        logger.warning("ADMIN_MSG: sender is None, skipping")
        return

    user_id = event.message.sender.user_id
    chat_id = event.message.recipient.chat_id
    job_text = event.message.body.text if event.message.body else None

    logger.info(f"ADMIN_MSG: user_id={user_id}, chat_id={chat_id}")
    logger.info(f"ADMIN_MSG: user_id==ADMIN_ID? {user_id == ADMIN_ID}")
    logger.info(f"ADMIN_MSG: chat_id==GROUP_ID? {chat_id == GROUP_ID}")
    logger.info(f"ADMIN_MSG: text={job_text[:50] if job_text else None}")

    if user_id != ADMIN_ID:
        logger.info("ADMIN_MSG: not admin, skipping")
        return

    if chat_id == GROUP_ID:
        logger.info("ADMIN_MSG: sent to group, skipping")
        await event.message.answer("❌ Отправляйте заявки мне в личку, а не в группу!")
        return

    if not job_text:
        logger.info("ADMIN_MSG: no text")
        await event.message.answer("❌ Отправьте текстовое сообщение с описанием заявки.")
        return

    group_text = build_group_message(job_text, "free", created_at=datetime.now().isoformat())
    attachments = build_job_keyboard("free")

    logger.info(f"ADMIN_MSG: sending to GROUP_ID={GROUP_ID}")
    logger.info(f"ADMIN_MSG: text length={len(group_text)}")
    logger.info(f"ADMIN_MSG: attachments={attachments is not None}")

    try:
        response = await bot.send_message(
            chat_id=GROUP_ID,
            text=group_text,
            attachments=attachments
        )

        logger.info(f"ADMIN_MSG: response type={type(response)}")
        logger.info(f"ADMIN_MSG: response={response}")

        # Проверяем все возможные пути к message_id
        if hasattr(response, 'message'):
            logger.info(f"ADMIN_MSG: response.message={response.message}")
            if response.message:
                logger.info(f"ADMIN_MSG: response.message.body={response.message.body}")
                if response.message.body:
                    logger.info(f"ADMIN_MSG: response.message.body.mid={response.message.body.mid}")
                    group_message_id = str(response.message.body.mid)
                else:
                    logger.warning("ADMIN_MSG: response.message.body is None")
                    group_message_id = None
            else:
                logger.warning("ADMIN_MSG: response.message is None")
                group_message_id = None
        else:
            logger.warning("ADMIN_MSG: response has no message attribute")
            group_message_id = None

        # Альтернативные пути
        if not group_message_id:
            for attr in ['message_id', 'id', 'mid']:
                if hasattr(response, attr):
                    val = getattr(response, attr)
                    logger.info(f"ADMIN_MSG: response.{attr}={val}")

        if group_message_id:
            jobs_db[group_message_id] = {
                "status": "free",
                "text": job_text,
                "group_text": group_text,
                "user_id": None,
                "user_name": None,
                "take_type": None,
                "admin_msg_id": None,
                "created_at": datetime.now().isoformat()
            }

            logger.info(f"ADMIN_MSG: saved to jobs_db, keys now={list(jobs_db.keys())}")

            await event.message.answer(
                f"✅ Заявка опубликована в группе!\n\n"
                f"ID сообщения: {group_message_id}"
            )
        else:
            logger.warning("ADMIN_MSG: could not get message_id")
            await event.message.answer("⚠️ Заявка отправлена, но не удалось получить ID сообщения.")

    except Exception as e:
        logger.error(f"ADMIN_MSG ERROR: {e}", exc_info=True)
        await event.message.answer(f"❌ Ошибка публикации: {e}")


# ==================== ОБРАБОТКА CALLBACK'ОВ ====================

@dp.message_callback()
async def handle_callback(event: MessageCallback):
    """Обработка нажатий на inline-кнопки."""
    logger.info("=" * 60)
    logger.info("CALLBACK RECEIVED")
    logger.info("=" * 60)

    callback: Callback = event.callback
    callback_data = callback.payload
    user = callback.user
    user_id = user.user_id
    user_name = get_user_name(user)

    logger.info(f"CALLBACK: user_id={user_id}, user_name={user_name}")
    logger.info(f"CALLBACK: payload={callback_data}")

    try:
        data = json.loads(callback_data) if callback_data else {}
    except json.JSONDecodeError as e:
        logger.error(f"CALLBACK: JSON parse error: {e}")
        data = {}

    action = data.get("action")
    take_type = data.get("type")

    logger.info(f"CALLBACK: action={action}, take_type={take_type}")
    logger.info(f"CALLBACK: jobs_db keys={list(jobs_db.keys())}")
    logger.info(f"CALLBACK: jobs_db content={jobs_db}")

    message: Optional[Message] = event.message
    if not message:
        logger.warning("CALLBACK: no message in event")
        await event.answer(notification="❌ Ошибка: не найдено сообщение")
        return

    message_id = message.body.mid if message.body else None
    chat_id = message.recipient.chat_id if message.recipient else None

    logger.info(f"CALLBACK: message_id={message_id}, chat_id={chat_id}")
    logger.info(f"CALLBACK: chat_id==GROUP_ID? {chat_id == GROUP_ID}")

    if not message_id:
        logger.warning("CALLBACK: no message_id")
        await event.answer(notification="❌ Ошибка: не найден ID сообщения")
        return

    if chat_id != GROUP_ID:
        logger.info(f"CALLBACK: ignored — chat_id {chat_id} != GROUP_ID {GROUP_ID}")
        return

    msg_id_str = str(message_id)
    job = jobs_db.get(msg_id_str)

    logger.info(f"CALLBACK: msg_id_str={msg_id_str}, job found={job is not None}")

    if not job:
        logger.warning(f"CALLBACK: job not found for msg_id={msg_id_str}")
        await event.answer(notification="❌ Заявка не найдена")
        return

    logger.info(f"CALLBACK: job status={job.get('status')}")

    # === БРОНИРОВАНИЕ ===
    if action == "take":
        logger.info("CALLBACK TAKE: processing...")

        if job["status"] != "free":
            logger.info(f"CALLBACK TAKE: job not free, status={job['status']}")
            await event.answer(notification="❌ Заявка уже забронирована или закрыта")
            return

        job["status"] = "booked"
        job["user_id"] = user_id
        job["user_name"] = user_name
        job["take_type"] = take_type

        type_label = "вдвоём" if take_type == "pair" else "один"

        updated_text = build_group_message(
            job["text"], "booked", user_name=user_name,
            take_type=take_type, created_at=job.get("created_at")
        )

        logger.info(f"CALLBACK TAKE: editing message {message_id}")

        try:
            await message.edit(
                text=updated_text,
                attachments=[]
            )
            logger.info("CALLBACK TAKE: message edited")

            await event.answer(notification=f"✅ Вы забронировали заявку ({type_label})!")

            admin_text = (
                "🔔 Новая бронь!\n\n"
                f"📋 Заявка: {job['text'][:100]}{'...' if len(job['text']) > 100 else ''}\n\n"
                f"👤 Исполнитель: {user_name}\n"
                f"🔗 Профиль: https://max.me/{user_id}\n"
                f"📌 Тип: {type_label}\n\n"
                "Нажмите кнопку \"Закрыть\" после завершения работы."
            )

            admin_attachments = build_admin_keyboard(msg_id_str)

            logger.info(f"CALLBACK TAKE: sending to admin {ADMIN_ID}")
            admin_response = await bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                attachments=admin_attachments
            )

            admin_msg_id = None
            if hasattr(admin_response, 'message') and admin_response.message and admin_response.message.body:
                admin_msg_id = str(admin_response.message.body.mid)

            job["admin_msg_id"] = admin_msg_id
            logger.info(f"CALLBACK TAKE: admin_msg_id={admin_msg_id}")

        except Exception as e:
            logger.error(f"CALLBACK TAKE ERROR: {e}", exc_info=True)
            job["status"] = "free"
            job["user_id"] = None
            await event.answer(notification="❌ Произошла ошибка, попробуйте позже")

    # === ЗАКРЫТИЕ ===
    elif action == "close":
        logger.info("CALLBACK CLOSE: processing...")

        job_msg_id = data.get("job_msg_id")
        logger.info(f"CALLBACK CLOSE: job_msg_id={job_msg_id}")

        if not job_msg_id:
            await event.answer(notification="❌ Ошибка: не найдена заявка")
            return

        if user_id != ADMIN_ID:
            logger.info(f"CALLBACK CLOSE: user {user_id} != admin {ADMIN_ID}")
            await event.answer(notification="❌ Только администратор может закрывать заявки")
            return

        job_msg_id_str = str(job_msg_id)
        job_to_close = jobs_db.get(job_msg_id_str)

        if not job_to_close:
            logger.warning(f"CALLBACK CLOSE: job not found for {job_msg_id_str}")
            await event.answer(notification="❌ Заявка не найдена")
            return

        job_to_close["status"] = "closed"

        closed_text = (
            "✅ ЗАКРЫТО\n"
            "━━━━━━━━━━━━━━\n\n"
            f"{job_to_close['text']}\n\n"
            "━━━━━━━━━━━━━━\n"
            "❗️ Заявка выполнена"
        )

        try:
            logger.info(f"CALLBACK CLOSE: editing group msg {job_msg_id}")
            await bot.edit_message(
                message_id=job_msg_id,
                text=closed_text
            )
            logger.info("CALLBACK CLOSE: group msg edited")

            if job_to_close.get("admin_msg_id"):
                text = job_to_close['text'][:100]
                if len(job_to_close['text']) > 100:
                    text += "..."
                logger.info(f"CALLBACK CLOSE: editing admin msg {job_to_close['admin_msg_id']}")
                await bot.edit_message(
                    message_id=job_to_close["admin_msg_id"],
                    text=f"✅ Заявка закрыта\n\n{text}"
                )

            await event.answer(notification="✅ Заявка закрыта!")
            logger.info("CALLBACK CLOSE: done")

        except Exception as e:
            logger.error(f"CALLBACK CLOSE ERROR: {e}", exc_info=True)
            await event.answer(notification="❌ Ошибка закрытия заявки")

    else:
        logger.info(f"CALLBACK: unknown action={action}")
        await event.answer(notification="❌ Неизвестное действие")


# ==================== ЗАПУСК ====================

async def main():
    logger.info("=" * 60)
    logger.info("BOT STARTING")
    logger.info(f"ADMIN_ID={ADMIN_ID}, GROUP_ID={GROUP_ID}")
    logger.info("=" * 60)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
