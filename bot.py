"""
MAX Bot Moderator
Автоматически удаляет сообщения от пользователей, которые не являются администраторами чата
"""
"""
MAX Bot Moderator - ИСПРАВЛЕННАЯ ВЕРСИЯ
Автоматически удаляет сообщения от пользователей, которые не являются администраторами чата
"""

import os
import asyncio
import logging
from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated, BotStarted, Command

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем токен из переменной окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден! Добавьте его в переменные окружения")

# Инициализация
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Кэш администраторов
CACHE_DURATION = 300  # 5 минут
admin_cache = {}

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

def get_chat_id_from_message(message):
    """Получает chat_id из объекта message"""
    # Пробуем разные варианты структуры
    if hasattr(message, 'recipient') and hasattr(message.recipient, 'chat_id'):
        return message.recipient.chat_id
    elif hasattr(message, 'chat') and hasattr(message.chat, 'chat_id'):
        return message.chat.chat_id
    elif hasattr(message, 'chat_id'):
        return message.chat_id
    else:
        logger.error(f"Не удалось получить chat_id из message: {dir(message)}")
        return None

def is_cache_valid(chat_id):
    """Проверяет валидность кэша"""
    import time
    key = f"admins_{chat_id}"
    if key not in admin_cache:
        return False
    cache_time = admin_cache[key].get('timestamp', 0)
    return (time.time() - cache_time) < CACHE_DURATION

def get_cached_admins(chat_id):
    """Получает админов из кэша"""
    key = f"admins_{chat_id}"
    if is_cache_valid(chat_id):
        return admin_cache[key].get('admins', [])
    return None

def set_cached_admins(chat_id, admin_ids):
    """Сохраняет админов в кэш"""
    import time
    key = f"admins_{chat_id}"
    admin_cache[key] = {
        'admins': admin_ids,
        'timestamp': time.time()
    }

async def fetch_admins_from_api(chat_id):
    """Запрашивает администраторов из API"""
    import aiohttp
    url = f"https://platform-api.max.ru/chats/{chat_id}/members/admins"
    headers = {"Authorization": BOT_TOKEN}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    admins = data.get('admins', [])
                    admin_ids = [admin.get('user_id') for admin in admins]
                    logger.info(f"✅ Получено {len(admin_ids)} админов для chat={chat_id}")
                    return admin_ids
                else:
                    logger.warning(f"⚠️ Ошибка API {response.status} для chat={chat_id}")
                    return []
    except Exception as e:
        logger.error(f"❌ Ошибка запроса админов: {e}")
        return []

async def get_admin_ids(chat_id):
    """Получает список ID администраторов"""
    cached = get_cached_admins(chat_id)
    if cached is not None:
        return cached
    
    admin_ids = await fetch_admins_from_api(chat_id)
    set_cached_admins(chat_id, admin_ids)
    return admin_ids

async def delete_message(message_id):
    """Удаляет сообщение"""
    import aiohttp
    url = f"https://platform-api.max.ru/messages?message_id={message_id}"
    headers = {"Authorization": BOT_TOKEN}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('success', False)
                return False
    except Exception as e:
        logger.error(f"❌ Ошибка удаления: {e}")
        return False

# ============================================
# ОБРАБОТЧИКИ
# ============================================

@dp.bot_started()
async def bot_started(event: BotStarted):
    """Старт бота"""
    logger.info(f"🤖 Бот запущен в chat={event.chat_id}")
    await event.bot.send_message(
        chat_id=event.chat_id,
        text='🛡️ *Бот-менеджер активирован!*\n\n'
             '✅ Только администраторы могут писать\n'
             '✂️ Сообщения остальных удаляются автоматически\n\n'
             'Команды: /help'
    )

@dp.message_created(Command('help'))
async def help_command(event: MessageCreated):
    """Справка"""
    await event.message.answer(
        '🛡️ *Бот-менеджер*\n\n'
        'Удаляет сообщения от неадминов.\n\n'
        'Команды:\n'
        '/help - Справка\n'
        '/status - Статус\n'
        '/myid - Ваш ID'
    )

@dp.message_created(Command('status'))
async def status_command(event: MessageCreated):
    """Статус"""
    chat_id = get_chat_id_from_message(event.message)
    if not chat_id:
        await event.message.answer("❌ Не удалось определить chat_id")
        return
    
    admin_ids = await get_admin_ids(chat_id)
    await event.message.answer(
        f'✅ Бот работает\n\n'
        f'Администраторов: {len(admin_ids)}'
    )

@dp.message_created(Command('myid'))
async def myid_command(event: MessageCreated):
    """Показать ID"""
    user_id = event.message.sender.user_id
    await event.message.answer(f"🆔 Ваш ID: `{user_id}`")

@dp.message_created()
async def check_message(event: MessageCreated):
    """Главная логика"""
    try:
        message = event.message
        user_id = message.sender.user_id
        message_id = message.message_id
        text = message.text or ''
        
        # Пропускаем команды
        if text.startswith('/'):
            return
        
        # Получаем chat_id
        chat_id = get_chat_id_from_message(message)
        if not chat_id:
            logger.warning("⚠️ Не удалось получить chat_id")
            return
        
        # Получаем админов
        admin_ids = await get_admin_ids(chat_id)
        
        # Проверяем права
        if user_id in admin_ids:
            return  # Админ - пропускаем
        
        # НЕ админ - удаляем
        success = await delete_message(message_id)
        if success:
            logger.info(f"✂️ Удалено: user={user_id}, chat={chat_id}")
        else:
            logger.warning(f"⚠️ Не удалось удалить: {message_id}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)

# ============================================
# ЗАПУСК
# ============================================

async def main():
    logger.info("🚀 Запуск бота...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
