"""
MAX Bot Moderator - DEBUG VERSION
"""

import os
import asyncio
import logging
import json
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

def log_object_structure(obj, name="Object"):
    """Логирует структуру объекта для отладки"""
    try:
        logger.info(f"=== Структура {name} ===")
        logger.info(f"Type: {type(obj)}")
        logger.info(f"Attributes: {[attr for attr in dir(obj) if not attr.startswith('_')]}")
        
        # Пытаемся получить dict
        if hasattr(obj, 'dict'):
            logger.info(f"Dict: {obj.dict()}")
        elif hasattr(obj, '__dict__'):
            logger.info(f"__dict__: {obj.__dict__}")
        
        # Пытаемся получить model_dump (pydantic v2)
        if hasattr(obj, 'model_dump'):
            logger.info(f"model_dump: {obj.model_dump()}")
    except Exception as e:
        logger.error(f"Ошибка логирования структуры: {e}")

def get_message_id_from_event(event):
    """Ищет message_id во всех возможных местах"""
    
    # Логируем структуру первый раз
    if not hasattr(get_message_id_from_event, '_logged'):
        log_object_structure(event, "Event")
        if hasattr(event, 'message'):
            log_object_structure(event.message, "Message")
        get_message_id_from_event._logged = True
    
    # Варианты поиска message_id
    candidates = []
    
    # 1. В самом событии
    if hasattr(event, 'message_id'):
        candidates.append(('event.message_id', event.message_id))
    
    # 2. В объекте message
    if hasattr(event, 'message'):
        msg = event.message
        if hasattr(msg, 'id'):
            candidates.append(('message.id', msg.id))
        if hasattr(msg, 'message_id'):
            candidates.append(('message.message_id', msg.message_id))
        if hasattr(msg, 'msg_id'):
            candidates.append(('message.msg_id', msg.msg_id))
        if hasattr(msg, 'msgId'):
            candidates.append(('message.msgId', msg.msgId))
    
    # 3. Через dict/model_dump
    try:
        if hasattr(event, 'model_dump'):
            dump = event.model_dump()
            if 'message_id' in dump:
                candidates.append(('dump.message_id', dump['message_id']))
            if 'message' in dump and isinstance(dump['message'], dict):
                for key in ['id', 'message_id', 'msg_id', 'msgId']:
                    if key in dump['message']:
                        candidates.append((f'dump.message.{key}', dump['message'][key]))
    except:
        pass
    
    # Логируем найденные варианты
    if candidates:
        logger.info(f"🔍 Найдено кандидатов message_id: {candidates}")
        # Возвращаем первый не-None
        for source, value in candidates:
            if value is not None:
                logger.info(f"✅ Используем message_id из {source}: {value}")
                return value
    
    logger.warning("❌ message_id не найден ни в одном месте!")
    return None

def get_message_info(event):
    """Извлекает информацию из события"""
    try:
        message_id = get_message_id_from_event(event)
        
        # chat_id
        chat_id = None
        if hasattr(event, 'chat_id'):
            chat_id = event.chat_id
        elif hasattr(event, 'message') and hasattr(event.message, 'recipient'):
            if hasattr(event.message.recipient, 'chat_id'):
                chat_id = event.message.recipient.chat_id
        
        # user_id
        user_id = None
        if hasattr(event, 'user_id'):
            user_id = event.user_id
        elif hasattr(event, 'message') and hasattr(event.message, 'sender'):
            if hasattr(event.message.sender, 'user_id'):
                user_id = event.message.sender.user_id
        
        # text
        text = ''
        if hasattr(event, 'message') and hasattr(event.message, 'text'):
            text = event.message.text or ''
        
        return {
            'message_id': message_id,
            'chat_id': chat_id,
            'user_id': user_id,
            'text': text
        }
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения: {e}", exc_info=True)
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
                    logger.info(f"✅ Админов: {len(admin_ids)}")
                    return admin_ids
                return []
    except Exception as e:
        logger.error(f"❌ API error: {e}")
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
        logger.error(f"❌ Delete error: {e}")
        return False

# ============================================
# ОБРАБОТЧИКИ
# ============================================

@dp.bot_started()
async def bot_started(event: BotStarted):
    logger.info(f"🤖 Старт в chat={event.chat_id}")
    try:
        await event.bot.send_message(
            chat_id=event.chat_id,
            text='🛡️ Бот-менеджер активен!\nТолько админы могут писать.'
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")

@dp.message_created(Command('help'))
async def help_command(event: MessageCreated):
    await event.message.answer(
        '🛡️ Бот-менеджер\n\n'
        'Команды:\n'
        '/help - Справка\n'
        '/status - Статус\n'
        '/myid - ID\n'
        '/debug - Отладка'
    )

@dp.message_created(Command('status'))
async def status_command(event: MessageCreated):
    info = get_message_info(event)
    if not info:
        await event.message.answer("❌ Ошибка")
        return
    admin_ids = await get_admin_ids(info['chat_id'])
    await event.message.answer(f'✅ Работает\nАдминов: {len(admin_ids)}')

@dp.message_created(Command('myid'))
async def myid_command(event: MessageCreated):
    info = get_message_info(event)
    if info:
        await event.message.answer(f"🆔 ID: {info['user_id']}")

@dp.message_created(Command('debug'))
async def debug_command(event: MessageCreated):
    info = get_message_info(event)
    text = f"🔍 Debug:\n"
    text += f"msg_id: {info['message_id']}\n"
    text += f"chat: {info['chat_id']}\n"
    text += f"user: {info['user_id']}"
    await event.message.answer(text)

@dp.message_created()
async def check_message(event: MessageCreated):
    """Главная логика"""
    try:
        info = get_message_info(event)
        if not info:
            return
        
        message_id = info['message_id']
        chat_id = info['chat_id']
        user_id = info['user_id']
        text = info['text']
        
        # Пропускаем команды
        if text and text.startswith('/'):
            return
        
        # Проверяем данные
        if not message_id:
            logger.warning(f"⚠️ Нет message_id! chat={chat_id}, user={user_id}")
            return
        
        if not all([chat_id, user_id]):
            logger.warning(f"⚠️ Неполные данные")
            return
        
        # Получаем админов
        admin_ids = await get_admin_ids(chat_id)
        
        # Проверяем
        if user_id in admin_ids:
            logger.info(f"✅ Админ: {user_id}")
            return
        
        # Удаляем
        success = await delete_message(message_id)
        if success:
            logger.info(f"✂️ УДАЛЕНО: user={user_id}, msg={message_id}")
        else:
            logger.warning(f"⚠️ Не удалось удалить: {message_id}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)

async def main():
    logger.info("🚀 Запуск бота...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
