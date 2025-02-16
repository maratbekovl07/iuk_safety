import time
import logging
import asyncio
import sqlite3
import re
import os
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ChatPermissions

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен вашего бота (замените на реальный токен)
BOT_TOKEN = "7576156238:AAHGtPvrqOsRZDUbu9Ea6T0UdmJObvooJ74"

# Список запрещённых слов (точное совпадение)
BANNED_WORDS = {
    "блядь", "блять", "блядки", "бляди", "блядство",
    "сука", "суки", "сукин сын",
    "хуй", "хуя", "хую", "хуйло", "хуйник", "хуйня",
    "пизда", "пизды", "пиздец", "пиздеть", "пиздатый", "пиздюк",
    "ебать", "ебаный", "ебан", "ебало", "еблан", "ебанат", "ебашить", "ебошить",
    "ёб", "ёб твою", "ёб его", "ёб меня", "ёбнулся", "въебать", "въебывать",
    "выёбывать", "выебывать", "выебан",
    "говно", "говнюк", "говняный", "дерьмо",
    "мудак", "мудозвон",
    "гандон",
    "хуесос", "хуяк",
    "пидор", "пидарас", "педераст", "педик", "пидоры",
    "лох",
    "шлюха", "шлюшка",
    "хер", "херня",
    "нахуя", "нахуй",
    "жопа", "жопу", "жопка",
    "соси", "соси мой", "соси меня",
    "мразь", "подонок",
}

# Список доверенных ID администраторов (если администраторы работают с личных аккаунтов)
ADMIN_IDS = {650963487}  # Здесь укажите ID, если они отправляют команды не анонимно

# ID основного администратора (для команды /restart)
MAIN_ADMIN_ID = 650963487  # Замените на актуальный ID

# Имя файла базы данных
DB_NAME = "warnings.db"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# -------------------------
# Вспомогательная функция проверки прав администратора
# -------------------------
def is_admin(message: types.Message) -> bool:
    # Если сообщение отправлено анонимно (sender_chat присутствует), считаем, что это админ
    if message.sender_chat is not None:
        return True
    # Если отправитель указан, проверяем его ID
    if message.from_user is not None:
        return message.from_user.id in ADMIN_IDS
    return False


# -------------------------
# Работа с SQLite (синхронно)
# -------------------------

def init_db_sync():
    """Создаёт таблицу предупреждений, если её ещё нет."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_warnings (
            chat_id INTEGER,
            user_id INTEGER,
            warnings INTEGER,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    conn.commit()
    conn.close()

async def init_db():
    await asyncio.to_thread(init_db_sync)
    logger.info("База данных инициализирована.")

def get_user_warnings_sync(chat_id: int, user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT warnings FROM user_warnings WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )
    row = cursor.fetchone()
    conn.close()
    return row

def insert_warning_sync(chat_id: int, user_id: int, warnings: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_warnings (chat_id, user_id, warnings) VALUES (?, ?, ?)",
        (chat_id, user_id, warnings)
    )
    conn.commit()
    conn.close()

def update_warning_sync(chat_id: int, user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_warnings SET warnings = warnings + 1 WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()

def delete_warnings_sync(chat_id: int, user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM user_warnings WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()

# -------------------------
# Проверка нецензурной лексики
# -------------------------
def check_profanity(text: str) -> bool:
    text = text.lower()
    banned_words_pattern = r'\b(' + '|'.join(map(re.escape, BANNED_WORDS)) + r')\b'
    return bool(re.search(banned_words_pattern, text, flags=re.UNICODE))

# -------------------------
# Обработчики команд администраторов
# -------------------------

@dp.message(F.text.startswith("/unban"), F.reply_to_message)
async def unban_user(message: types.Message):
    if not is_admin(message):
        await message.reply("❌ У вас нет прав для разблокировки пользователей.")
        return

    # Попытка получить целевого пользователя из ответа
    target_user = message.reply_to_message.from_user
    if target_user is None:
        target_user = message.reply_to_message.sender_chat  # если сообщение от анонимного пользователя

    try:
        # Для restrict_chat_member нужен числовой идентификатор
        target_id = target_user.id if hasattr(target_user, "id") else target_user
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
        )
        await asyncio.to_thread(delete_warnings_sync, message.chat.id, target_id)
        name = getattr(target_user, 'first_name', getattr(target_user, 'title', 'Пользователь'))
        await message.answer(
            f"✅ <a href='tg://user?id={target_id}'>{name}</a> успешно разблокирован.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при разблокировке пользователя: {e}")
        await message.reply(f"❌ Не удалось разблокировать пользователя: {e}")

@dp.message(F.text.startswith("/mute"), F.reply_to_message)
async def mute_user(message: types.Message):
    if not is_admin(message):
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Укажите продолжительность мьюта, например: /mute 1h")
        return

    duration_arg = args[1].strip()
    match = re.match(r'^(\d+)(h)$', duration_arg, flags=re.IGNORECASE)
    if not match:
        await message.reply("❌ Неверный формат. Используйте, например: 1h для 1 часа.")
        return

    hours = int(match.group(1))
    until_date = int(time.time() + hours * 3600)
    target_user = message.reply_to_message.from_user
    if target_user is None:
        target_user = message.reply_to_message.sender_chat

    try:
        target_id = target_user.id if hasattr(target_user, "id") else target_user
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            ),
            until_date=until_date
        )
        name = getattr(target_user, 'first_name', getattr(target_user, 'title', 'Пользователь'))
        await message.reply(
            f"✅ <a href='tg://user?id={target_id}'>{name}</a> замьючен на {hours} часов.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при мьюте пользователя: {e}")
        await message.reply(f"❌ Не удалось замьютить пользователя: {e}")

@dp.message(F.text.startswith("/ban"), F.reply_to_message)
async def ban_user(message: types.Message):
    if not is_admin(message):
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Укажите продолжительность бана, например: /ban 1h")
        return

    duration_arg = args[1].strip()
    match = re.match(r'^(\d+)(h)$', duration_arg, flags=re.IGNORECASE)
    if not match:
        await message.reply("❌ Неверный формат. Используйте, например: 1h для 1 часа.")
        return

    hours = int(match.group(1))
    until_date = int(time.time() + hours * 3600)
    target_user = message.reply_to_message.from_user
    if target_user is None:
        target_user = message.reply_to_message.sender_chat

    try:
        target_id = target_user.id if hasattr(target_user, "id") else target_user
        await bot.ban_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            until_date=until_date
        )
        name = getattr(target_user, 'first_name', getattr(target_user, 'title', 'Пользователь'))
        await message.reply(
            f"✅ <a href='tg://user?id={target_id}'>{name}</a> забанен на {hours} часов.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при бане пользователя: {e}")
        await message.reply(f"❌ Не удалось забанить пользователя: {e}")

# -------------------------
# Команда /restart для основного администратора (только не анонимно)
# -------------------------
@dp.message(F.text.startswith("/restart"))
async def restart_bot(message: types.Message):
    if not message.from_user or message.from_user.id != MAIN_ADMIN_ID:
        await message.reply("❌ У вас нет прав для перезагрузки бота. Команду /restart можно отправлять только с личного аккаунта основного администратора.")
        return

    await message.reply("✅ Перезагрузка бота...")
    logger.info("Бот перезагружается по команде основного администратора.")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# -------------------------
# Универсальный обработчик сообщений (проверка нецензурной лексики)
# -------------------------
@dp.message(F.text)
async def handle_message(message: types.Message):
    # Если сообщение — команда, пропускаем его
    if message.text.startswith("/"):
        return

    if message.chat.type not in ["group", "supergroup"]:
        return

    if not check_profanity(message.text):
        return

    chat_id = message.chat.id
    # Если сообщение от реального пользователя, берем его ID, иначе оставляем None
    user_id = message.from_user.id if message.from_user else None
    name = message.from_user.first_name if message.from_user else getattr(message.sender_chat, "title", "Пользователь")

    row = await asyncio.to_thread(get_user_warnings_sync, chat_id, user_id) if user_id else None

    if row is None:
        if user_id:
            await asyncio.to_thread(insert_warning_sync, chat_id, user_id, 1)
        await message.answer(
            f"{name}, вы использовали ненормативную лексику. При повторном нарушении вы будете заблокированы на 1 час."
        )
    else:
        warnings = row[0]
        if warnings == 1:
            until_date = int(time.time() + 3600)  # 1 час
            try:
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
                await message.answer(
                    f"<a href='tg://user?id={user_id}'>{name}</a> заблокирован на 1 час за использование ненормативной лексики.",
                    parse_mode='HTML'
                )
                await asyncio.to_thread(update_warning_sync, chat_id, user_id)
            except Exception as e:
                logger.error(f"Ошибка при блокировке пользователя {user_id} в чате {chat_id}: {e}")
        else:
            await message.answer(
                f"{name}, ваше предыдущее нарушение уже зафиксировано."
            )

# -------------------------
# Основная функция запуска бота
# -------------------------
async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
