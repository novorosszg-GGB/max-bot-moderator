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

# ================== API ЗАПРОСЫ (ТЕСТОВАЯ ВЕРСИЯ) ==================

async def fetch_admins_method_1(chat_id: str) -> list:
    """Метод 1: GET /chats/{chatId}/members/admins"""
    url = f"{API_URL}/chats/{chat_id}/members/admins"
    headers = {"Authorization": BOT_TOKEN}
    
    logger.info(f"🧪 [МЕТОД 1] Пробуем /members/admins для chat_id={chat_id}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                status = response.status
                text = await response.text()
                
                logger.info(f"📡 [МЕТОД 1] Статус: {status}")
                logger.info(f"📡 [МЕТОД 1] Ответ (первые 500 символов): {text[:500]}")
                
                if status == 200:
                    data = await response.json()
                    admins = data.get('admins', [])
                    admin_ids = [admin['user_id'] for admin in admins]
                    logger.info(f"✅ [МЕТОД 1] Получено {len(admin_ids)} админов: {admin_ids}")
                    return admin_ids
                else:
                    logger.warning(f"⚠️ [МЕТОД 1] Ошибка {status}: {text[:200]}")
                    return []
    except Exception as e:
        logger.error(f"❌ [МЕТОД 1] Исключение: {e}")
        return []

async def fetch_admins_method_2(chat_id: str) -> list:
    """Метод 2: GET /chats/{chatId}/members (все участники) → фильтр is_admin"""
    url = f"{API_URL}/chats/{chat_id}/members"
    headers = {"Authorization": BOT_TOKEN}
    params = {"count": 100}  # Получаем до 100 участников
    
    logger.info(f"🧪 [МЕТОД 2] Пробуем /members (все участники) для chat_id={chat_id}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                status = response.status
                text = await response.text()
                
                logger.info(f"📡 [МЕТОД 2] Статус: {status}")
                logger.info(f"📡 [МЕТОД 2] Ответ (первые 500 символов): {text[:500]}")
                
                if status == 200:
                    data = await response.json()
                    members = data.get('members', [])
                    
                    logger.info(f"📊 [МЕТОД 2] Всего участников: {len(members)}")
                    
                    # Фильтруем админов и владельцев
                    admin_ids = []
                    for member in members:
                        user_id = member.get('user_id')
                        is_admin = member.get('is_admin', False)
                        is_owner = member.get('is_owner', False)
                        first_name = member.get('first_name', 'Unknown')
                        
                        logger.info(
                            f"👤 [МЕТОД 2] user_id={user_id}, "
                            f"name={first_name}, "
                            f"is_admin={is_admin}, "
                            f"is_owner={is_owner}"
                        )
                        
                        if is_admin or is_owner:
                            admin_ids.append(user_id)
                    
                    logger.info(f"✅ [МЕТОД 2] Найдено {len(admin_ids)} админов: {admin_ids}")
                    return admin_ids
                else:
                    logger.warning(f"⚠️ [МЕТОД 2] Ошибка {status}: {text[:200]}")
                    return []
    except Exception as e:
        logger.error(f"❌ [МЕТОД 2] Исключение: {e}")
        return []

async def fetch_admins_from_api(chat_id: str) -> list:
    """Основная функция: пробует оба метода и оба формата chat_id"""
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🔍 НАЧАЛО ПОЛУЧЕНИЯ АДМИНОВ ДЛЯ chat_id={chat_id}")
    logger.info(f"{'='*60}\n")
    
    # Пробуем исходный chat_id
    logger.info(f"🧪 Попытка 1: Исходный chat_id = {chat_id}")
    
    admins_1 = await fetch_admins_method_1(chat_id)
    if admins_1:
        logger.info(f"✅ УСПЕХ с методом 1 и исходным chat_id!")
        return admins_1
    
    admins_2 = await fetch_admins_method_2(chat_id)
    if admins_2:
        logger.info(f"✅ УСПЕХ с методом 2 и исходным chat_id!")
        return admins_2
    
    # Если chat_id отрицательный, пробуем положительный
    if str(chat_id).startswith('-'):
        positive_chat_id = str(chat_id)[1:]  # Убираем минус
        logger.info(f"\n🧪 Попытка 2: Положительный chat_id = {positive_chat_id}")
        
        admins_1 = await fetch_admins_method_1(positive_chat_id)
        if admins_1:
            logger.info(f"✅ УСПЕХ с методом 1 и положительным chat_id!")
            return admins_1
        
        admins_2 = await fetch_admins_method_2(positive_chat_id)
        if admins_2:
            logger.info(f"✅ УСПЕХ с методом 2 и положительным chat_id!")
            return admins_2
    
    logger.error(f"❌ НЕ УДАЛОСЬ получить админов ни одним способом")
    logger.info(f"\n{'='*60}\n")
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
        
        logger.info(
            f"📨 Извлечено: msg_id={msg_id}, chat={chat_id}, "
            f"user={user_id}, text={text[:30] if text else 'None'}..."
        )
        
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
        "👋 **Бот-модератор запущен! (ТЕСТОВАЯ ВЕРСИЯ)**\n\n"
        "Могут писать только администраторы.\n"
        "Сообщения остальных будут удалены автоматически.\n\n"
        "📊 Эта версия показывает детальные логи проверки.\n\n"
        "Команды: /help, /test"
    )

@dp.message_created()
async def check_message(event: MessageCreated):
    """Проверяет и удаляет сообщения от не-админов"""
    msg_id, chat_id, user_id, text = get_message_info(event)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🔍 ПРОВЕРКА СООБЩЕНИЯ")
    logger.info(f"{'='*60}")
    logger.info(f"📨 Message ID: {msg_id}")
    logger.info(f"💬 Chat ID: {chat_id}")
    logger.info(f"👤 User ID: {user_id}")
    logger.info(f"📝 Text: {text}")
    logger.info(f"{'='*60}\n")
    
    # Проверки
    if not msg_id:
        logger.warning("⚠️ Не удалось получить message_id, пропускаем")
        return
    
    if not chat_id or not user_id:
        logger.warning("⚠️ Нет chat_id или user_id, пропускаем")
        return
    
    # Пропускаем команды
    if text and text.startswith('/'):
        logger.info(f"⏭️ Пропускаем команду: {text}")
        return
    
    # Получаем список админов
    logger.info(f"🔍 НАЧИНАЕМ ПОЛУЧЕНИЕ СПИСКА АДМИНОВ...")
    admin_ids = await get_admin_ids(str(chat_id))
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📋 РЕЗУЛЬТАТ ПОЛУЧЕНИЯ АДМИНОВ:")
    logger.info(f"{'='*60}")
    logger.info(f"Найдено админов: {len(admin_ids)}")
    logger.info(f"Список admin_ids: {admin_ids}")
    logger.info(f"Тип admin_ids: {[type(aid).__name__ for aid in admin_ids]}")
    logger.info(f"{'='*60}\n")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"🔍 ПРОВЕРКА ПРАВ ПОЛЬЗОВАТЕЛЯ")
    logger.info(f"{'='*60}")
    logger.info(f"User ID из сообщения: {user_id}")
    logger.info(f"Тип user_id: {type(user_id).__name__}")
    logger.info(f"{'='*60}\n")
    
    # Проверяем права (с учётом типов)
    is_admin = False
    
    # Проверка 1: Прямое сравнение
    if user_id in admin_ids:
        is_admin = True
        logger.info(f"✅ [ПРОВЕРКА 1] user_id найден в admin_ids (прямое сравнение)")
    else:
        logger.info(f"❌ [ПРОВЕРКА 1] user_id НЕ найден (прямое сравнение)")
    
    # Проверка 2: Преобразование в строку
    if str(user_id) in [str(aid) for aid in admin_ids]:
        is_admin = True
        logger.info(f"✅ [ПРОВЕРКА 2] user_id найден (сравнение строк)")
    else:
        logger.info(f"❌ [ПРОВЕРКА 2] user_id НЕ найден (сравнение строк)")
    
    # Проверка 3: Преобразование в int
    try:
        if int(user_id) in [int(aid) for aid in admin_ids]:
            is_admin = True
            logger.info(f"✅ [ПРОВЕРКА 3] user_id найден (сравнение int)")
        else:
            logger.info(f"❌ [ПРОВЕРКА 3] user_id НЕ найден (сравнение int)")
    except:
        logger.info(f"⚠️ [ПРОВЕРКА 3] Не удалось преобразовать в int")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 ИТОГОВОЕ РЕШЕНИЕ:")
    logger.info(f"{'='*60}")
    
    if is_admin:
        logger.info(f"✅ User {user_id} — АДМИНИСТРАТОР, сообщение оставляем")
        logger.info(f"{'='*60}\n")
        return
    
    # Удаляем сообщение
    logger.info(f"🚫 User {user_id} — НЕ АДМИНИСТРАТОР")
    logger.info(f"🗑️ Удаляем сообщение {msg_id}")
    logger.info(f"{'='*60}\n")
    
    await delete_message(msg_id)

# ================== КОМАНДЫ ==================
@dp.message_created()
async def handle_help(event: MessageCreated):
    """Команда /help"""
    _, chat_id, _, text = get_message_info(event)
    if text == '/help':
        await send_message(
            chat_id,
            "📖 **Команды бота (ТЕСТОВАЯ ВЕРСИЯ):**\n\n"
            "/help — эта справка\n"
            "/status — статус бота\n"
            "/test — тест получения админов\n"
            "/myid — ваш ID"
        )

@dp.message_created()
async def handle_test(event: MessageCreated):
    """Команда /test - принудительное обновление админов"""
    _, chat_id, _, text = get_message_info(event)
    if text == '/test':
        # Удаляем кэш
        if str(chat_id) in admin_cache:
            del admin_cache[str(chat_id)]
        
        # Получаем заново с детальным логированием
        admin_ids = await get_admin_ids(str(chat_id))
        
        await send_message(
            chat_id,
            f"🧪 **Тест завершён!**\n\n"
            f"Найдено админов: {len(admin_ids)}\n"
            f"Список ID: {admin_ids}\n\n"
            f"📊 Проверьте логи на BotHost.ru для деталей"
        )

@dp.message_created()
async def handle_status(event: MessageCreated):
    """Команда /status"""
    _, chat_id, _, text = get_message_info(event)
    if text == '/status':
        cached = get_cached_admins(str(chat_id))
        status_text = "✅ **Статус бота (ТЕСТОВАЯ ВЕРСИЯ):**\n\n"
        status_text += f"Бот работает\n"
        status_text += f"Кэш: {'активен' if cached else 'пуст'}\n"
        if cached:
            status_text += f"Админов в кэше: {len(cached)}"
        await send_message(chat_id, status_text)

@dp.message_created()
async def handle_myid(event: MessageCreated):
    """Команда /myid"""
    _, chat_id, user_id, text = get_message_info(event)
    if text == '/myid':
        await send_message(chat_id, f"🆔 Ваш ID: `{user_id}`\nТип: {type(user_id).__name__}")

# ================== ЗАПУСК ==================
async def main():
    logger.info("🚀 Запуск MAX бота-менеджера (ТЕСТОВАЯ ВЕРСИЯ)...")
    logger.info(f"📝 Токен: {'✅ Найден' if BOT_TOKEN else '❌ Отсутствует'}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
