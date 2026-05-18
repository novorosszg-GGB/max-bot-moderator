import os
import asyncio
import logging

from typing import Set

from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен MAX-бота из редактируемых переменных BotHost
BOT_TOKEN = os.environ.get("MY_MAX_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "Не найден MY_MAX_BOT_TOKEN. Укажите реальный токен MAX-бота в дополнительных переменных окружения."
    )

# Ручной список администраторов из переменной MY_ADMIN_IDS
# Пример значения в BotHost: 18577787,60239084,69548956
ADMIN_IDS_RAW = os.environ.get("MY_ADMIN_IDS", "")

MANUAL_ADMIN_IDS: Set[int] = {
    int(user_id.strip())
    for user_id in ADMIN_IDS_RAW.split(",")
    if user_id.strip().isdigit()
}

logger.info("Ручной список администраторов: %s", MANUAL_ADMIN_IDS)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


async def get_admins(chat_id: int) -> Set[int]:
    """
    Возвращает список администраторов.
    Используется ручной список из переменной MY_ADMIN_IDS.
    """

    if MANUAL_ADMIN_IDS:
        logger.info(
            "Используется ручной список администраторов для чата %s: %s",
            chat_id,
            MANUAL_ADMIN_IDS,
        )
        return MANUAL_ADMIN_IDS

    logger.warning(
        "MY_ADMIN_IDS не задан. Администраторы не определены для чата %s",
        chat_id,
    )
    return set()


async def delete_message_safe(message_id: str) -> bool:
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
    Удаляет сообщения от пользователей, которые не входят в MY_ADMIN_IDS.
    """

    try:
        message = event.message

        chat_id = message.recipient.chat_id
        user_id = message.sender.user_id
        message_id = message.body.mid
        text = message.body.text or ""

        logger.info(
            "Новое сообщение: chat_id=%s, message_id=%s, user_id=%s, text=%s",
            chat_id,
            message_id,
            user_id,
            text,
        )

        # Команды обрабатываем до удаления сообщений
        if text == "/status":
            admins = await get_admins(chat_id)
            await message.answer(
                f"Бот работает.\n"
                f"ID чата: {chat_id}\n"
                f"Ваш ID: {user_id}\n"
                f"Администраторов найдено: {len(admins)}\n"
                f"Ваш статус: {'администратор' if user_id in admins else 'не администратор'}"
            )
            return

        if text == "/myid":
            await message.answer(f"Ваш ID: {user_id}")
            return

        if text == "/help":
            await message.answer(
                "Бот-модератор MAX.\n\n"
                "Удаляет сообщения всех пользователей, кроме разрешённых администраторов.\n\n"
                "Команды:\n"
                "/help — справка\n"
                "/status — статус бота\n"
                "/myid — показать ваш ID"
            )
            return

        admins = await get_admins(chat_id)

        if user_id in admins:
            logger.info("Сообщение администратора разрешено: user_id=%s", user_id)
            return

        logger.info(
            "Пользователь %s не входит в список администраторов. Удаляем сообщение %s",
            user_id,
            message_id,
        )
        await delete_message_safe(message_id)

    except Exception as error:
        logger.error("Ошибка в обработчике сообщения: %s", error)


async def main():
    logger.info("Запуск MAX бота-модератора...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
