"""
MAX Bot Moderator - ФИНАЛЬНАЯ ВЕРСИЯ
"""

import os
import asyncio
import logging
from maxapi import Bot, Dispatcher
from maxapi.types import MessageCreated, BotStarted, Command

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден!")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

CACHE_DURATION = 300
admin_cache = {}

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

def get_message_info(event):
    """Извлекает всю нужную информацию из события"""
    try:
        message = event.message
        
        # Получаем ID сообщения
        msg_id = None
        if hasattr(message, 'id'):
            msg_id = message.id
        elif hasattr(message, 'message_id'):
            msg_id = message.message_id
        elif hasattr(event, 'message_id'):
            msg_id = event.message_id
        
        # Получаем chat_id
        chat_id = None
        if hasattr(event, 'chat_id'):
            chat_id = event.chat_id
        elif hasattr(message, 'recipient') and hasattr(message.recipient, 'chat_id'):
            chat_id = message.recipient.chat_id
        elif hasattr(message, 'chat') and hasattr(message.chat, 'chat_id'):
            chat_id = message.chat.chat_id
        
        # Получаем user_id
        user_id = None
        if hasattr(message, 'sender') and hasattr(message.sender, 'user_id'):
            user_id = message.sender.user_id
        elif hasattr(event, 'user_id'):
            user_id = event.user_id
        
        # Получаем текст
        text = message.text if hasattr(message, 'text') else ''
        
        return {
            'message_id': msg_id,
            'chat_id': chat_id,
            'user_id': user_id,
            'text': text
        }
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения данных: {e}")
        logger.error(f"Event attributes: {dir(event)}")
        logger.error(f"Message attributes: {dir(event.message) if hasattr(event, 'message') else 'No message'}")
        return None

def is_cache_valid(chat_id):
    import time
    key = f"admins_{chat_id}"
    if key not in admin_cache:
        return False
    cache_time = admin_cache[key].get('timestamp', 0)
    return (time.time() - cache_time) < CACHE_DURATION

def get_cached_admins(chat_id):
    key = f"admins_{chat_id}"
    if is_cache_valid(chat_id):
        return admin_cache[key].get('admins', [])
    return None

def set_cached_admins(chat_id, admin_ids):
    import time
    key = f"admins_{chat_id}"
    admin_cache[key] = {
        'admins': admin_ids,
        'timestamp': time.time()
    }

async def fetch_admins_from_api(chat_id):
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
                    logger.info(f"✅ Админов: {len(admin_ids)} для chat={chat_id}")
                    return admin_ids
                else:
                    logger.warning(f"⚠️ API error {response.status}")
                    return []
    except Exception as e:
        logger.error(f"❌ Ошибка API: {e}")
        return []

async def get_admin_ids(chat_id):
    cached = get_cached_admins(chat_id)
    if cached is not None:
        return cached
    
    admin_ids = await fetch_admins_from_api(chat_id)
    set_cached_admins(chat_id, admin_ids)
    return admin_ids

async def delete_message(message_id):
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
    logger.info(f"🤖 Бот запущен в chat={event.chat_id}")
    try:
        await event.bot.send_message(
            chat_id=event.chat_id,
            text='🛡️ *Бот-менеджер активирован!*\n\n'
                 '✅ Только администраторы могут писать\n'
                 '✂️ Сообщения остальных удаляются\n\n'
                 'Команды: /help'
        )
    except Exception as e:
        logger.error(f"Ошибка отправки приветствия: {e}")

@dp.message_created(Command('help'))
async def help_command(event: MessageCreated):
    await event.message.answer(
        '🛡️ *Бот-менеджер*\n\n'
        'Команды:\n'
        '/help - Справка\n'
        '/status - Статус\n'
        '/myid - Ваш ID\n'
        '/debug - Отладка (для проверки)'
    )

@dp.message_created(Command('status'))
async def status_command(event: MessageCreated):
    info = get_message_info(event)
    if not info or not info['chat_id']:
        await event.message.answer("❌ Не удалось определить chat_id")
        return
    
    admin_ids = await get_admin_ids(info['chat_id'])
    await event.message.answer(
        f'✅ Бот работает\n'
        f'Администраторов: {len(admin_ids)}'
    )

@dp.message_created(Command('myid'))
async def myid_command(event: MessageCreated):
    info = get_message_info(event)
    if info and info['user_id']:
        await event.message.answer(f"🆔 Ваш ID: `{info['user_id']}`")

@dp.message_created(Command('debug'))
async def debug_command(event: MessageCreated):
    """Отладочная информация"""
    info = get_message_info(event)
    debug_text = f"🔍 *Debug Info:*\n\n"
    debug_text += f"message_id: {info['message_id']}\n"
    debug_text += f"chat_id: {info['chat_id']}\n"
    debug_text += f"user_id: {info['user_id']}\n"
    debug_text += f"text: {info['text']}\n"
    await event.message.answer(debug_text)

@dp.message_created()
async def check_message(event: MessageCreated):
    """Главная логика"""
    try:
        # Получаем информацию о сообщении
        info = get_message_info(event)
        
        if not info:
            logger.error("⚠️ Не удалось получить информацию о сообщении")
            return
        
        message_id = info['message_id']
        chat_id = info['chat_id']
        user_id = info['user_id']
        text = info['text']
        
        # Пропускаем команды
        if text and text.startswith('/'):
            return
        
        # Проверяем наличие всех данных
        if not all([message_id, chat_id, user_id]):
            logger.warning(f"⚠️ Неполные данные: msg_id={message_id}, chat={chat_id}, user={user_id}")
            return
        
        # Получаем админов
        admin_ids = await get_admin_ids(chat_id)
        
        # Проверяем права
        if user_id in admin_ids:
            logger.info(f"✅ Админ пишет: user={user_id}")
            return
        
        # НЕ админ - удаляем
        success = await delete_message(message_id)
        if success:
            logger.info(f"✂️ УДАЛЕНО: user={user_id}, chat={chat_id}, msg_id={message_id}")
        else:
            logger.warning(f"⚠️ Не удалось удалить: msg_id={message_id}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)

# ============================================
# ЗАПУСК
# ============================================

async def main():
    logger.info("🚀 Запуск MAX бота-менеджера...")
    logger.info(f"📝 Токен: {'✅ Найден' if BOT_TOKEN else '❌ Не найден'}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
