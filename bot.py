"""
MAX Bot Moderator
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

# Получаем токен из переменной окружения (безопасно!)
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден! Добавьте его в переменные окружения на BotHost.ru")

# Инициализация бота
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Время кэширования списка администраторов (в секундах)
CACHE_DURATION = 300  # 5 минут

# Кэш для хранения списка администраторов
admin_cache = {}

# ============================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С КЭШЕМ АДМИНИСТРАТОРОВ
# ============================================

def get_cache_key(chat_id):
    """Генерирует ключ для кэша"""
    return f"admins_{chat_id}"

def is_cache_valid(chat_id):
    """Проверяет, действителен ли кэш"""
    key = get_cache_key(chat_id)
    if key not in admin_cache:
        return False
    
    import time
    cache_time = admin_cache[key].get('timestamp', 0)
    return (time.time() - cache_time) < CACHE_DURATION

def get_cached_admins(chat_id):
    """Получает список администраторов из кэша"""
    key = get_cache_key(chat_id)
    if is_cache_valid(chat_id):
        logger.info(f"📦 Админы получены из кэша для chat={chat_id}")
        return admin_cache[key].get('admins', [])
    return None

def set_cached_admins(chat_id, admin_ids):
    """Сохраняет список администраторов в кэш"""
    import time
    key = get_cache_key(chat_id)
    admin_cache[key] = {
        'admins': admin_ids,
        'timestamp': time.time()
    }
    logger.info(f"💾 Кэш обновлен для chat={chat_id}, админов: {len(admin_ids)}")

def clear_cache(chat_id):
    """Очищает кэш для конкретного чата"""
    key = get_cache_key(chat_id)
    if key in admin_cache:
        del admin_cache[key]
        logger.info(f"🗑️ Кэш очищен для chat={chat_id}")

async def fetch_admins_from_api(chat_id):
    """Запрашивает список администраторов из MAX API"""
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
                    logger.info(f"✅ Получено {len(admin_ids)} администраторов для chat={chat_id}")
                    return admin_ids
                else:
                    logger.warning(f"⚠️ Ошибка API: статус {response.status} для chat={chat_id}")
                    return []
    except Exception as e:
        logger.error(f"❌ Ошибка при запросе админов: {e}")
        return []

async def get_admin_ids(chat_id):
    """Получает список ID администраторов (из кэша или API)"""
    # Сначала проверяем кэш
    cached = get_cached_admins(chat_id)
    if cached is not None:
        return cached
    
    # Если кэш пуст или устарел - запрашиваем из API
    admin_ids = await fetch_admins_from_api(chat_id)
    
    # Сохраняем в кэш
    set_cached_admins(chat_id, admin_ids)
    
    return admin_ids

# ============================================
# ОБРАБОТЧИКИ СОБЫТИЙ
# ============================================

@dp.bot_started()
async def bot_started(event: BotStarted):
    """Обработчик старта бота в чате"""
    logger.info(f"🤖 Бот запущен в chat={event.chat_id}")
    
    await event.bot.send_message(
        chat_id=event.chat_id,
        text='🛡️ *Бот-менеджер активирован!*\n\n'
             '✅ Только администраторы могут писать в этом чате\n'
             '✂️ Сообщения остальных удаляются автоматически\n'
             '🔄 Список админов обновляется каждые 5 минут\n\n'
             'Команды: /help'
    )

@dp.message_created(Command('help'))
async def help_command(event: MessageCreated):
    """Команда помощи"""
    help_text = """
🛡️ *Бот-менеджер для MAX*

Бот автоматически удаляет сообщения от пользователей, 
которые не являются администраторами чата.

📋 *Команды:*
/help - Показать это сообщение
/status - Статус бота
/myid - Узнать свой ID
/refresh - Обновить список админов (только для админов)

🔧 *Как работает:*
• Бот проверяет каждое сообщение
• Если отправитель не администратор - сообщение удаляется
• Список администраторов кэшируется на 5 минут

⚙️ *Технические детали:*
• Скорость удаления: ~0.5-1 сек
• Кэш администраторов: 5 минут
• Платформа: BotHost.ru
    """
    await event.message.answer(help_text)

@dp.message_created(Command('status'))
async def status_command(event: MessageCreated):
    """Статус бота"""
    chat_id = event.message.chat.chat_id
    admin_ids = await get_admin_ids(chat_id)
    
    import datetime
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    status_text = f"""
✅ *Бот работает нормально*

📊 *Статистика:*
• Администраторов в чате: {len(admin_ids)}
• Время кэша: {CACHE_DURATION // 60} минут
• Текущее время: {current_time}

🔄 Кэш обновляется автоматически
    """
    await event.message.answer(status_text)

@dp.message_created(Command('myid'))
async def myid_command(event: MessageCreated):
    """Показать ID пользователя"""
    user_id = event.message.sender.user_id
    await event.message.answer(f"🆔 Ваш ID: `{user_id}`")

@dp.message_created(Command('refresh'))
async def refresh_command(event: MessageCreated):
    """Принудительное обновление списка администраторов"""
    chat_id = event.message.chat.chat_id
    user_id = event.message.sender.user_id
    
    # Проверяем, является ли пользователь администратором
    admin_ids = await get_admin_ids(chat_id)
    
    if user_id not in admin_ids:
        await event.message.answer("⛔ У вас нет прав на эту команду")
        return
    
    # Очищаем кэш и загружаем свежий список
    clear_cache(chat_id)
    new_admin_ids = await get_admin_ids(chat_id)
    
    await event.message.answer(
        f"✅ *Список администраторов обновлен*\n\n"
        f"Найдено администраторов: {len(new_admin_ids)}"
    )

@dp.message_created()
async def check_message(event: MessageCreated):
    """Главная логика: проверка и удаление сообщений от не-админов"""
    try:
        message = event.message
        user_id = message.sender.user_id
        chat_id = message.chat.chat_id
        message_id = message.message_id
        text = message.text or ''
        
        # Пропускаем команды (они обрабатываются отдельно)
        if text.startswith('/'):
            return
        
        # Получаем список администраторов
        admin_ids = await get_admin_ids(chat_id)
        
        # Проверяем, является ли пользователь администратором
        if user_id in admin_ids:
            # Администратор - пропускаем
            return
        
        # НЕ администратор - удаляем сообщение
        success = await delete_message(message_id)
        
        if success:
            logger.info(f"✂️ Удалено сообщение: user={user_id}, chat={chat_id}, text='{text[:30]}...'")
        else:
            logger.warning(f"⚠️ Не удалось удалить сообщение: {message_id}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке сообщения: {e}")

async def delete_message(message_id):
    """Удаляет сообщение через MAX API"""
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
        logger.error(f"❌ Ошибка удаления сообщения: {e}")
        return False

# ============================================
# ЗАПУСК БОТА
# ============================================

async def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск MAX бота-менеджера...")
    logger.info(f"📝 Токен: {'✅ Найден' if BOT_TOKEN else '❌ Не найден'}")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
