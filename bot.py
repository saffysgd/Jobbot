import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any

from maxapi import Bot, Dispatcher, F
from maxapi.types import MessageCreated, CallbackQuery, Command, BotStarted

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

# Проверяем, что ID группы со знаком минус
if GROUP_ID > 0:
    GROUP_ID = -GROUP_ID

# Хранилище заявок в памяти (для production рекомендуется Redis/БД)
# Структура: {message_id_in_group: {"status": "free|booked|closed", "user_id": None, "admin_msg_id": None}}
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

def build_job_keyboard(status: str = "free") -> Optional[dict]:
    """Создаёт inline-клавиатуру для заявки."""
    if status in ("booked", "closed"):
        return None

    return {
        "buttons": [
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
    }


def build_admin_notification(job_text: str, user_info: dict, take_type: str) -> str:
    """Формирует текст уведомления для администратора."""
    type_label = "вдвоём" if take_type == "pair" else "один"
    user_name = user_info.get("name", "Неизвестно")
    user_link = f"https://max.me/{user_info.get('id', '')}"

    return (
        f"🔔 Новая бронь!\n\n"
        f"📋 Заявка: {job_text[:100]}{'...' if len(job_text) > 100 else ''}\n\n"
        f"👤 Исполнитель: {user_name}\n"
        f"🔗 Профиль: {user_link}\n"
        f"📌 Тип: {type_label}\n\n"
        f"Нажмите кнопку \"Закрыть\" после завершения работы."
    )


def build_closed_message(original_text: str) -> str:
    """Формирует текст закрытой заявки."""
    return f"✅ ЗАКРЫТО\n\n{original_text}\n\n❗️ Заявка выполнена"


def build_group_message(job_text: str, status: str, user_name: Optional[str] = None,
                        take_type: Optional[str] = None, created_at: Optional[str] = None) -> str:
    """Формирует текст сообщения в группе в зависимости от статуса."""
    time_str = created_at[:16].replace("T", " ") if created_at else datetime.now().strftime("%d.%m.%Y %H:%M")

    if status == "free":
        return (
            f"📢 НОВАЯ ЗАЯВКА\n"
            f"⏰ {time_str}\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"{job_text}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"🟢 Статус: Свободно"
        )
    elif status == "booked":
        type_label = "вдвоём" if take_type == "pair" else "один"
        return (
            f"📢 ЗАЯВКА\n"
            f"⏰ {time_str}\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"{job_text}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"🟡 Статус: Забронировано ({type_label})\n"
            f"👤 Исполнитель: {user_name or 'Неизвестно'}"
        )
    elif status == "closed":
        return (
            f"✅ ЗАКРЫТО\n"
            f"⏰ {time_str}\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"{job_text}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"❗️ Заявка выполнена"
        )
    return job_text


# ==================== ОБРАБОТЧИКИ ====================

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    """Приветствие при старте бота."""
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="👋 Привет! Я бот для управления заявками.\n\n"
             "Администраторы могут отправлять мне тексты заявок, "
             "а я буду публиковать их в группе с кнопками для исполнителей."
    )


@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    """Обработка команды /start."""
    user_id = event.message.sender.user_id

    if user_id == ADMIN_ID:
        await event.message.answer(
            "👨‍💼 Панель администратора\n\n"
            "Отправьте мне текст заявки — я опубликую её в группе.\n\n"
            "Когда исполнитель нажмёт \"Беру\" или \"Беру вдвоём\", "
            "вы получите уведомление с его контактом.\n\n"
            "После завершения работы нажмите \"Закрыть\" в уведомлении."
        )
    else:
        await event.message.answer(
            "🤖 Я бот для управления заявками.\n\n"
            "Заявки публикуются в рабочей группе. "
            "Нажимайте кнопки под заявками, чтобы взять их в работу."
        )


@dp.message_created()
async def handle_admin_message(event: MessageCreated):
    """Обработка сообщений от администратора (новые заявки)."""
    user_id = event.message.sender.user_id

    # Игнорируем сообщения от обычных пользователей и из группы
    if user_id != ADMIN_ID:
        return
    if event.message.chat_id == GROUP_ID:
        await event.message.answer("❌ Отправляйте заявки мне в личку, а не в группу!")
        return

    job_text = event.message.body.text
    if not job_text:
        await event.message.answer("❌ Отправьте текстовое сообщение с описанием заявки.")
        return

    # Формируем текст заявки для группы
    group_text = build_group_message(job_text, "free", created_at=datetime.now().isoformat())
    keyboard = build_job_keyboard("free")

    # Отправляем в группу
    try:
        attachments = []
        if keyboard:
            attachments.append({"type": "inline_keyboard", "payload": keyboard})

        response = await bot.send_message(
            chat_id=GROUP_ID,
            text=group_text,
            attachments=attachments if attachments else None
        )

        group_message_id = str(response.get("message_id") or response.get("id"))
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
                f"✅ Заявка опубликована в группе!\n\n"
                f"ID сообщения: {group_message_id}"
            )
            logger.info(f"Job published: msg_id={group_message_id}, admin={ADMIN_ID}")
        else:
            await event.message.answer("⚠️ Заявка отправлена, но не удалось получить ID сообщения.")

    except Exception as e:
        logger.error(f"Failed to publish job: {e}")
        await event.message.answer(f"❌ Ошибка публикации: {e}")


# ==================== ОБРАБОТКА CALLBACK'ОВ ====================

@dp.callback_query()
async def handle_callback(event: CallbackQuery):
    """Обработка нажатий на inline-кнопки."""
    callback_data = event.callback_query.data
    user = event.callback_query.from_user
    user_id = user.user_id
    user_name = user.name or f"User_{user_id}"

    try:
        data = json.loads(callback_data) if callback_data else {}
    except json.JSONDecodeError:
        data = {}

    action = data.get("action")
    take_type = data.get("type")

    message_id = event.callback_query.message.message_id if event.callback_query.message else None
    chat_id = event.callback_query.message.chat_id if event.callback_query.message else None

    if not message_id or not chat_id:
        await event.callback_query.answer(text="❌ Ошибка: не найдено сообщение")
        return

    if chat_id != GROUP_ID:
        return

    msg_id_str = str(message_id)
    job = jobs_db.get(msg_id_str)
    if not job:
        await event.callback_query.answer(text="❌ Заявка не найдена")
        return

    # === БРОНИРОВАНИЕ (Беру / Беру вдвоём) ===
    if action == "take":
        if job["status"] != "free":
            await event.callback_query.answer(text="❌ Заявка уже забронирована или закрыта")
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
            await bot.edit_message_text(
                chat_id=GROUP_ID,
                message_id=message_id,
                text=updated_text
            )

            await event.callback_query.answer(
                text=f"✅ Вы забронировали заявку ({type_label})!"
            )

            # Уведомление админу с кнопкой "Закрыть"
            admin_text = build_admin_notification(job["text"], {
                "id": user_id, "name": user_name
            }, take_type)

            admin_keyboard = {
                "buttons": [
                    [
                        {
                            "type": "callback",
                            "text": "🔒 Закрыть заявку",
                            "payload": json.dumps({"action": "close", "job_msg_id": message_id})
                        }
                    ]
                ]
            }

            admin_msg = await bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                attachments=[{"type": "inline_keyboard", "payload": admin_keyboard}]
            )

            admin_msg_id = str(admin_msg.get("message_id") or admin_msg.get("id"))
            job["admin_msg_id"] = admin_msg_id

            logger.info(
                f"Job booked: msg_id={message_id}, user={user_name}({user_id}), "
                f"type={take_type}, admin_notified={admin_msg_id}"
            )

        except Exception as e:
            logger.error(f"Failed to process booking: {e}")
            job["status"] = "free"
            job["user_id"] = None
            await event.callback_query.answer(text="❌ Произошла ошибка, попробуйте позже")

    # === ЗАКРЫТИЕ ЗАЯВКИ (админ нажимает "Закрыть") ===
    elif action == "close":
        job_msg_id = data.get("job_msg_id")

        if not job_msg_id:
            await event.callback_query.answer(text="❌ Ошибка: не найдена заявка")
            return

        # Проверяем, что закрывает админ
        if user_id != ADMIN_ID:
            await event.callback_query.answer(text="❌ Только администратор может закрывать заявки")
            return

        job_msg_id_str = str(job_msg_id)
        job_to_close = jobs_db.get(job_msg_id_str)
        if not job_to_close:
            await event.callback_query.answer(text="❌ Заявка не найдена")
            return

        job_to_close["status"] = "closed"

        closed_text = build_closed_message(job_to_close["text"])

        try:
            # Обновляем сообщение в группе
            await bot.edit_message_text(
                chat_id=GROUP_ID,
                message_id=job_msg_id,
                text=closed_text
            )

            # Удаляем кнопки у админа (редактируем сообщение уведомления)
            if job_to_close.get("admin_msg_id"):
                await bot.edit_message_text(
                    chat_id=ADMIN_ID,
                    message_id=job_to_close["admin_msg_id"],
                    text=f"✅ Заявка закрыта\n\n{job_to_close['text'][:100]}..."
                )

            await event.callback_query.answer(text="✅ Заявка закрыта!")
            logger.info(f"Job closed: msg_id={job_msg_id}, admin={ADMIN_ID}")

        except Exception as e:
            logger.error(f"Failed to close job: {e}")
            await event.callback_query.answer(text="❌ Ошибка закрытия заявки")


# ==================== ЗАПУСК ====================

async def main():
    logger.info("Bot starting...")
    logger.info(f"ADMIN_ID={ADMIN_ID}, GROUP_ID={GROUP_ID}")

    # Определяем режим работы: polling или webhook
    amvera_env = os.environ.get("AMVERA", "0")

    if amvera_env == "1":
        # Amvera — используем polling (webhook требует HTTPS + домен)
        logger.info("Running in Amvera mode (polling)")
        await dp.start_polling(bot)
    else:
        # Локально — polling
        logger.info("Running in local mode (polling)")
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
