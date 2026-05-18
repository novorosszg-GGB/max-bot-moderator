import os
import asyncio
import logging
import time

from typing import Set, Dict, Optional

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения BotHost
# Токен MAX-бота из редактируемых переменных BotHost
BOT_TOKEN = os.environ.get("MY_MAX_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Не найден MY_MAX_BOT_TOKEN. Укажите реальный токен MAX-бота в дополнительных переменных окружения.")
# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Кэш администраторов: chat_id -> {"admins": set(user_ids), "time": timestamp}
admin_cache: Dict[int, Dict[str, object]] = {}

# Время жизни кэша администраторов — 5 минут
CACHE_TTL = 300


async def get_admins(chat_id: int) -> Set[int]:
    """
    Получает список администраторов чата.
    Кэширует результат на 5 минут.
    """
    now = time.time()

    cached = admin_cache.get(chat_id)
    if cached and now - cached["time"] < CACHE_TTL:
        return cached["admins"]

    try:
        admins = await bot.get_chat_admins(chat_id)
        admin_ids = {admin.user_id for admin in admins}

        admin_cache[chat_id] = {
            "admins": admin_ids,
            "time": now,
        }

        logger.info("Обновлен список администраторов чата %s: %s", chat_id, admin_ids)

        return admin_ids

    except Exception as error:
        logger.error("Ошибка при получении администраторов чата %s: %s", chat_id, error)
        return set()


async def delete_message_safe(message_id: int) -> bool:
    """
    Безопасно удаляет сообщение.
    """
    try:
        await bot.delete_message(message_id)
        logger.info("Удалено сообщение %s", message_id)
        return True

    except Exception as error:
        logger.error("Ошибка при удалении сообщения %s: %s", message_id, error)
        return False


@dp.message_created()
async def handle_message_created(event: MessageCreated):
    """
    Обработчик новых сообщений.
    Удаляет сообщения от пользователей, которые не являются администраторами.
    """

    try:
        message = event.message
        chat_id = message.recipient.chat_id
      message_id = message.body.mid
        user_id = message.sender.user_id

        logger.info(
            "Новое сообщение: chat_id=%s, message_id=%s, user_id=%s",
            chat_id,
            message_id,
            user_id,
        )

        admins = await get_admins(chat_id)

        if user_id in admins:
            logger.info("Сообщение администратора разрешено: user_id=%s", user_id)
            return

        await delete_message_safe(message_id)

    except Exception as error:
        logger.error("Ошибка в обработчике сообщения: %s", error)


@dp.message_created(commands=["help"])
async def help_command(event: MessageCreated):
    await event.message.answer(
        "Бот-модератор MAX.\n\n"
        "Удаляет сообщения всех пользователей, кроме администраторов чата.\n\n"
        "Команды:\n"
        "/help — справка\n"
        "/status — статус бота\n"
        "/myid — показать ваш ID\n"
        "/refresh — обновить список администраторов"
    )


@dp.message_created(commands=["status"])
async def status_command(event: MessageCreated):
    chat_id = event.message.recipient.chat_id
    admins = await get_admins(chat_id)

    await event.message.answer(
        f"Бот работает.\n"
        f"ID чата: {chat_id}\n"
        f"Администраторов в кэше: {len(admins)}"
    )


@dp.message_created(commands=["myid"])
async def myid_command(event: MessageCreated):
    user_id = event.message.sender.user_id
    await event.message.answer(f"Ваш ID: {user_id}")


@dp.message_created(commands=["refresh"])
async def refresh_command(event: MessageCreated):
    chat_id = event.message.recipient.chat_id

    if chat_id in admin_cache:
        del admin_cache[chat_id]

    admins = await get_admins(chat_id)

    await event.message.answer(
        f"Список администраторов обновлен.\n"
        f"Администраторов найдено: {len(admins)}"
    )


async def main():
    logger.info("Запуск MAX бота-модератора...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(main())
