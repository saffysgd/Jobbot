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
)

# ==================== КОНФИГУРАЦИЯ ====================
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
GROUP_ID = int(os.environ.get("GROUP_ID", "0"))
TOKEN = os.environ.get("MAX_BOT_TOKEN", "")

if not TOKEN:
    raise ValueError("MAX_BOT_TOKEN не задан! Задайте переменную в Amvera → Переменные")
if ADMIN_ID == 0:
    raise ValueError("ADMIN_ID не задан! Задайте переменную в Amvera → Переменные")
if GROUP_ID == 0:
    raise ValueError("GROUP_ID не задан! Задайте переменную в Amvera → Переменные")

if GROUP_ID > 0:
    GROUP_ID = -GROUP_ID

# Хранилище заявок в памяти
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

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def build_job_keyboard(status: str = "free") -> Optional[list]:
    """Создаёт inline-клавиатуру для заявки."""
    if status in ("booked", "closed"):
        return None

    return [
        [
            {
                "type": "callback",
                "text": "🙋 Беру",
                "payload": json.dumps({"action": "take", "type": "single"})
            },
            {
                "type": "callback",
                "text": "👥 Беру вдвоём",
                "payload": json.dumps({"action": "take", "type": "pair"})
            }
        ],
        [
            {
                "type": "link",
                "text": "❓ Задать вопрос",
                "url": f"https://max.me/{ADMIN_ID}"
            }
        ]
    ]


def build_admin_notification(job_text: str, user_info: dict, take_type: str) -> str:
    """Формирует текст уведомления для администратора."""
    type_label = "вдвоём" if take_type == "pair" else "один"
    user_name = user_info.get("name", "Неизвестно")
    user_link = f"https://max.me/{user_info.get('id', '')}"

    return (
        f"🔔 Новая бронь!

"
        f"📋 Заявка: {job_text[:100]}{'...' if len(job_text) > 100 else ''}

"
        f"👤 Исполнитель: {user_name}
"
        f"🔗 Профиль: {user_link}
"
        f"📌 Тип: {type_label}

"
        f"Нажмите кнопку "Закрыть" после завершения работы."
    )


def build_group_message(job_text: str, status: str, user_name: Optional[str] = None,
                        take_type: Optional[str] = None, created_at: Optional[str] = None) -> str:
    """Формирует текст сообщения в группе в зависимости от статуса."""
    time_str = created_at[:16].replace("T", " ") if created_at else datetime.now().strftime("%d.%m.%Y %H:%M")

    if status == "free":
        return (
            f"📢 НОВАЯ ЗАЯВКА
"
            f"⏰ {time_str}
"
            f"━━━━━━━━━━━━━━

"
            f"{job_text}

"
            f"━━━━━━━━━━━━━━
"
            f"🟢 Статус: Свободно"
        )
    elif status == "booked":
        type_label = "вдвоём" if take_type == "pair" else "один"
        return (
            f"📢 ЗАЯВКА
"
            f"⏰ {time_str}
"
            f"━━━━━━━━━━━━━━

"
            f"{job_text}

"
            f"━━━━━━━━━━━━━━
"
            f"🟡 Статус: Забронировано ({type_label})
"
            f"👤 Исполнитель: {user_name or 'Неизвестно'}"
        )
    elif status == "closed":
        return (
            f"✅ ЗАКРЫТО
"
            f"⏰ {time_str}
"
            f"━━━━━━━━━━━━━━

"
            f"{job_text}

"
            f"━━━━━━━━━━━━━━
"
            f"❗️ Заявка выполнена"
        )
    return job_text


# ==================== ОБРАБОТЧИКИ ====================

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    """Приветствие при старте бота."""
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="👋 Привет! Я бот для управления заявками.

"
             "Администраторы могут отправлять мне тексты заявок, "
             "а я буду публиковать их в группе с кнопками для исполнителей."
    )


@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    """Обработка команды /start."""
    user_id = event.message.sender.user_id

    if user_id == ADMIN_ID:
        await event.message.answer(
            "👨‍💼 Панель администратора

"
            "Отправьте мне текст заявки — я опубликую её в группе.

"
            "Когда исполнитель нажмёт "Беру" или "Беру вдвоём", "
            "вы получите уведомление с его контактом.

"
            "После завершения работы нажмите "Закрыть" в уведомлении."
        )
    else:
        await event.message.answer(
            "🤖 Я бот для управления заявками.

"
            "Заявки публикуются в рабочей группе. "
            "Нажимайте кнопки под заявками, чтобы взять их в работу."
        )


@dp.message_created()
async def handle_admin_message(event: MessageCreated):
    """Обработка сообщений от администратора (новые заявки)."""
    user_id = event.message.sender.user_id

    if user_id != ADMIN_ID:
        return
    if event.message.chat_id == GROUP_ID:
        await event.message.answer("❌ Отправляйте заявки мне в личку, а не в группу!")
        return

    job_text = event.message.body.text
    if not job_text:
        await event.message.answer("❌ Отправьте текстовое сообщение с описанием заявки.")
        return

    group_text = build_group_message(job_text, "free", created_at=datetime.now().isoformat())
    keyboard = build_job_keyboard("free")

    try:
        response = await bot.send_message(
            chat_id=GROUP_ID,
            text=group_text,
            attachments=keyboard
        )

        group_message_id = str(response.message_id)
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

            await event.message.answer(
                f"✅ Заявка опубликована в группе!

"
                f"ID сообщения: {group_message_id}"
            )
            logger.info(f"Job published: msg_id={group_message_id}, admin={ADMIN_ID}")
        else:
            await event.message.answer("⚠️ Заявка отправлена, но не удалось получить ID сообщения.")

    except Exception as e:
        logger.error(f"Failed to publish job: {e}")
        await event.message.answer(f"❌ Ошибка публикации: {e}")


# ==================== ОБРАБОТКА CALLBACK'ОВ ====================

@dp.message_callback()
async def handle_callback(event: MessageCallback):
    """Обработка нажатий на inline-кнопки."""
    callback: Callback = event.callback
    callback_data = callback.payload
    user = callback.user
    user_id = user.user_id
    user_name = user.name or f"User_{user_id}"

    try:
        data = json.loads(callback_data) if callback_data else {}
    except json.JSONDecodeError:
        data = {}

    action = data.get("action")
    take_type = data.get("type")

    # Получаем сообщение, к которому привязан callback
    message: Optional[Message] = event.message
    if not message:
        await bot.send_callback(
            callback_id=callback.callback_id,
            notification="❌ Ошибка: не найдено сообщение"
        )
        return

    message_id = message.message_id
    chat_id = message.recipient.chat_id if message.recipient else None

    if chat_id != GROUP_ID:
        return

    msg_id_str = str(message_id)
    job = jobs_db.get(msg_id_str)
    if not job:
        await bot.send_callback(
            callback_id=callback.callback_id,
            notification="❌ Заявка не найдена"
        )
        return

    # === БРОНИРОВАНИЕ (Беру / Беру вдвоём) ===
    if action == "take":
        if job["status"] != "free":
            await bot.send_callback(
                callback_id=callback.callback_id,
                notification="❌ Заявка уже забронирована или закрыта"
            )
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

        try:
            # Редактируем сообщение в группе (убираем кнопки)
            await bot.edit_message(
                message_id=message_id,
                text=updated_text
            )

            await bot.send_callback(
                callback_id=callback.callback_id,
                notification=f"✅ Вы забронировали заявку ({type_label})!"
            )

            # Уведомление админу с кнопкой "Закрыть"
            admin_text = build_admin_notification(job["text"], {
                "id": user_id, "name": user_name
            }, take_type)

            admin_keyboard = [
                [
                    {
                        "type": "callback",
                        "text": "🔒 Закрыть заявку",
                        "payload": json.dumps({"action": "close", "job_msg_id": message_id})
                    }
                ]
            ]

            admin_msg = await bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                attachments=admin_keyboard
            )

            admin_msg_id = str(admin_msg.message_id)
            job["admin_msg_id"] = admin_msg_id

            logger.info(
                f"Job booked: msg_id={message_id}, user={user_name}({user_id}), "
                f"type={take_type}, admin_notified={admin_msg_id}"
            )

        except Exception as e:
            logger.error(f"Failed to process booking: {e}")
            job["status"] = "free"
            job["user_id"] = None
            await bot.send_callback(
                callback_id=callback.callback_id,
                notification="❌ Произошла ошибка, попробуйте позже"
            )

    # === ЗАКРЫТИЕ ЗАЯВКИ (админ нажимает "Закрыть") ===
    elif action == "close":
        job_msg_id = data.get("job_msg_id")

        if not job_msg_id:
            await bot.send_callback(
                callback_id=callback.callback_id,
                notification="❌ Ошибка: не найдена заявка"
            )
            return

        # Проверяем, что закрывает админ
        if user_id != ADMIN_ID:
            await bot.send_callback(
                callback_id=callback.callback_id,
                notification="❌ Только администратор может закрывать заявки"
            )
            return

        job_msg_id_str = str(job_msg_id)
        job_to_close = jobs_db.get(job_msg_id_str)
        if not job_to_close:
            await bot.send_callback(
                callback_id=callback.callback_id,
                notification="❌ Заявка не найдена"
            )
            return

        job_to_close["status"] = "closed"

        closed_text = (
            f"✅ ЗАКРЫТО
"
            f"━━━━━━━━━━━━━━

"
            f"{job_to_close['text']}

"
            f"━━━━━━━━━━━━━━
"
            f"❗️ Заявка выполнена"
        )

        try:
            # Обновляем сообщение в группе
            await bot.edit_message(
                message_id=job_msg_id,
                text=closed_text
            )

            # Удаляем кнопки у админа (редактируем сообщение уведомления)
            if job_to_close.get("admin_msg_id"):
                await bot.edit_message(
                    message_id=job_to_close["admin_msg_id"],
                    text=f"✅ Заявка закрыта

{job_to_close['text'][:100]}..."
                )

            await bot.send_callback(
                callback_id=callback.callback_id,
                notification="✅ Заявка закрыта!"
            )
            logger.info(f"Job closed: msg_id={job_msg_id}, admin={ADMIN_ID}")

        except Exception as e:
            logger.error(f"Failed to close job: {e}")
            await bot.send_callback(
                callback_id=callback.callback_id,
                notification="❌ Ошибка закрытия заявки"
            )


# ==================== ЗАПУСК ====================

async def main():
    logger.info("Bot starting...")
    logger.info(f"ADMIN_ID={ADMIN_ID}, GROUP_ID={GROUP_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
