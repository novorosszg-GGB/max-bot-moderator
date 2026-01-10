import os
import asyncio
import logging
from datetime import datetime, timedelta
import aiohttp
from maxapi import Bot, Dispatcher
from maxapi.types import BotStarted, MessageCreated

# ================== КОНФИГУРАЦИЯ ==================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в переменных окружения!")

API_URL = "https://platform-api.max.ru"
CACHE_DURATION = 300  # 5 минут

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================== КЭШИРОВАНИЕ ==================
admin_cache = {}

def is_cache_valid(chat_id: str) -> bool:
    """Проверяет валидность кэша для чата"""
    if chat_id not in admin_cache:
        return False
    cache_time = admin_cache[chat_id].get('timestamp')
    if not cache_time:
        return False
    return (datetime.now() - cache_time).total_seconds() < CACHE_DURATION

def get_cached_admins(chat_id: str):
    """Получает список админов из кэша"""
    if is_cache_valid(chat_id):
        logger.info(f"📦 Используем кэш админов для chat_id={chat_id}")
        return admin_cache[chat_id]['admin_ids']
    return None

def set_cached_admins(chat_id: str, admin_ids: list):
    """Сохраняет список админов в кэш"""
    admin_cache[chat_id] = {
        'admin_ids': admin_ids,
        'timestamp': datetime.now()
    }
    logger.info(f"💾 Кэш обновлён для chat_id={chat_id}: {len(admin_ids)} админов")

# ================== API ЗАПРОСЫ ==================
async def fetch_admins_from_api(chat_id: str) -> list:
    """Получает список администраторов через /chats/{chatId}/members"""
    url = f"{API_URL}/chats/{chat_id}/members"
    headers = {"Authorization": BOT_TOKEN}
    params = {"count": 100}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    members = data.get('members', [])
                    
                    # Фильтруем админов и владельцев
                    admin_ids = []
                    for member in members:
                        user_id = member.get('user_id')
                        is_admin = member.get('is_admin', False)
                        is_owner = member.get('is_owner', False)
                        
                        if is_admin or is_owner:
                            admin_ids.append(user_id)
                    
                    logger.info(f"✅ Получено {len(admin_ids)} админов для chat_id={chat_id}")
                    return admin_ids
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка получения админов: {response.status} - {error_text}")
                    return []
    except Exception as e:
        logger.error(f"❌ Исключение при запросе админов: {e}")
        return []

async def get_admin_ids(chat_id: str) -> list:
    """Получает список ID админов (с кэшированием)"""
    cached = get_cached_admins(chat_id)
    if cached is not None:
        return cached
    
    logger.info(f"🔄 Запрашиваем список админов для chat_id={chat_id}")
    admin_ids = await fetch_admins_from_api(chat_id)
    set_cached_admins(chat_id, admin_ids)
    return admin_ids

async def delete_message(message_id: str) -> bool:
    """Удаляет сообщение через MAX API"""
    url = f"{API_URL}/messages"
    headers = {"Authorization": BOT_TOKEN}
    params = {"message_id": message_id}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers, params=params) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('success'):
                        logger.info(f"🗑️ Сообщение {message_id} успешно удалено")
                        return True
                    else:
                        logger.warning(f"⚠️ Не удалось удалить {message_id}: {result.get('message')}")
                        return False
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка удаления: {response.status} - {error_text}")
                    return False
    except Exception as e:
        logger.error(f"❌ Исключение при удалении: {e}")
        return False

async def send_message(chat_id: int, text: str):
    """Отправляет сообщение в чат"""
    url = f"{API_URL}/messages"
    headers = {
        "Authorization": BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "chat_id": chat_id,
        "text": text,
        "format": "markdown"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка отправки: {response.status} - {error_text}")
    except Exception as e:
        logger.error(f"❌ Исключение при отправке: {e}")

# ================== ПОЛУЧЕНИЕ ДАННЫХ ==================
def get_message_info(event: MessageCreated):
    """Извлекает информацию из события MESSAGE_CREATED"""
    try:
        message = event.message
        
        # Message ID из body.mid
        msg_id = None
        if hasattr(message, 'body') and hasattr(message.body, 'mid'):
            msg_id = message.body.mid
        
        # Chat ID
        chat_id = None
        if hasattr(message, 'recipient') and hasattr(message.recipient, 'chat_id'):
            chat_id = message.recipient.chat_id
        elif hasattr(message, 'chat_id'):
            chat_id = message.chat_id
        
        # User ID
        user_id = None
        if hasattr(message, 'sender') and hasattr(message.sender, 'user_id'):
            user_id = message.sender.user_id
        elif hasattr(message, 'user_id'):
            user_id = message.user_id
        
        # Text
        text = None
        if hasattr(message, 'body') and hasattr(message.body, 'text'):
            text = message.body.text
        elif hasattr(message, 'text'):
            text = message.text
        
        return msg_id, chat_id, user_id, text
        
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения данных: {e}")
        return None, None, None, None

# ================== ОБРАБОТЧИКИ ==================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.bot_started()
async def handle_bot_started(event: BotStarted):
    """Обработка добавления бота в чат"""
    chat_id = event.chat_id
    logger.info(f"🤖 Бот запущен в chat={chat_id}")
    await send_message(
        chat_id,
        "✅ **Бот-модератор активен!**\n\n"
        "📋 Могут писать только администраторы.\n"
        "🗑️ Сообщения остальных будут удалены (~1 сек).\n\n"
        "Команды:\n"
        "/help — справка\n"
        "/status — статус бота\n"
        "/refresh — обновить список админов\n"
        "/myid — ваш ID"
    )

@dp.message_created()
async def check_message(event: MessageCreated):
    """Проверяет и удаляет сообщения от не-админов"""
    msg_id, chat_id, user_id, text = get_message_info(event)
    
    # Проверки
    if not msg_id or not chat_id or not user_id:
        return
    
    # Пропускаем команды
    if text and text.startswith('/'):
        return
    
    # Получаем список админов
    admin_ids = await get_admin_ids(str(chat_id))
    
    # Проверяем права
    if user_id in admin_ids:
        logger.info(f"✅ User {user_id} — админ, сообщение оставляем")
        return
    
    # Удаляем сообщение
    logger.info(f"🚫 User {user_id} НЕ админ, удаляем сообщение {msg_id}")
    await delete_message(msg_id)

# ================== КОМАНДЫ ==================
@dp.message_created()
async def handle_help(event: MessageCreated):
    """Команда /help"""
    _, chat_id, _, text = get_message_info(event)
    if text == '/help':
        await send_message(
            chat_id,
            "📖 **Команды бота:**\n\n"
            "/help — эта справка\n"
            "/status — статус бота и кэша\n"
            "/refresh — обновить список админов\n"
            "/myid — показать ваш ID"
        )

@dp.message_created()
async def handle_status(event: MessageCreated):
    """Команда /status"""
    _, chat_id, _, text = get_message_info(event)
    if text == '/status':
        cached = get_cached_admins(str(chat_id))
        status_text = "✅ **Статус бота:**\n\n"
        status_text += "🟢 Бот работает нормально\n"
        status_text += f"📦 Кэш: {'активен' if cached else 'пуст'}\n"
        if cached:
            status_text += f"👥 Админов в кэше: {len(cached)}\n"
            status_text += f"🔄 Обновление через: {CACHE_DURATION // 60} мин"
        await send_message(chat_id, status_text)

@dp.message_created()
async def handle_refresh(event: MessageCreated):
    """Команда /refresh"""
    _, chat_id, user_id, text = get_message_info(event)
    if text == '/refresh':
        admin_ids = await get_admin_ids(str(chat_id))
        
        if user_id in admin_ids:
            # Удаляем кэш
            if str(chat_id) in admin_cache:
                del admin_cache[str(chat_id)]
            
            # Обновляем
            new_admins = await get_admin_ids(str(chat_id))
            await send_message(
                chat_id,
                f"🔄 **Список админов обновлён!**\n\n"
                f"Найдено администраторов: {len(new_admins)}"
            )
        else:
            await send_message(chat_id, "❌ Только администраторы могут использовать эту команду")

@dp.message_created()
async def handle_myid(event: MessageCreated):
    """Команда /myid"""
    _, chat_id, user_id, text = get_message_info(event)
    if text == '/myid':
        await send_message(chat_id, f"🆔 Ваш ID: `{user_id}`")

# ================== ЗАПУСК ==================
async def main():
    logger.info("🚀 Запуск MAX бота-менеджера...")
    logger.info(f"📝 Токен: {'✅ Найден' if BOT_TOKEN else '❌ Отсутствует'}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
