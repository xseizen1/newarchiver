import os
import logging
import asyncio
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

import database

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

# ID владельца (админа) — тоже из переменных
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Хранилище для одноразовых медиа (временно)
temp_media: Dict[int, Dict[str, Any]] = {}

async def auth_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[bool]:
    """Декоратор для проверки авторизации"""
    user = update.effective_user
    if not user:
        return False
    
    user_id = user.id
    
    # Владелец всегда авторизован
    if user_id == OWNER_ID:
        return True
    
    # Проверка по базе
    if database.is_authorized(user_id):
        return True
    
    # Если не авторизован — шлём отказ
    if update.message:
        await update.message.reply_text(
            "⛔ У вас нет доступа к этому боту.\n"
            "Обратитесь к владельцу для добавления в белый список."
        )
    return False

# ============== КОМАНДЫ УПРАВЛЕНИЯ ДОСТУПОМ ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start"""
    user = update.effective_user
    
    # Проверяем авторизацию
    if not await auth_check(update, context):
        return
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я бот для отслеживания удалённых сообщений и одноразового медиа.\n\n"
        f"📋 Доступные команды:\n"
        f"/add_user [ID] — добавить пользователя в белый список (только для владельца)\n"
        f"/remove_user [ID] — удалить пользователя из белого списка (только для владельца)\n"
        f"/list_users — показать всех авторизованных пользователей (только для владельца)\n"
        f"/my_id — показать ваш Telegram ID\n"
        f"/help — показать эту справку"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /help"""
    if not await auth_check(update, context):
        return
    
    await start(update, context)

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ID пользователя"""
    if not await auth_check(update, context):
        return
    
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 Ваш Telegram ID: `{user.id}`\n"
        f"👤 Username: @{user.username or 'не указан'}\n"
        f"📝 Имя: {user.first_name}",
        parse_mode='Markdown'
    )

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет пользователя в белый список (только для владельца)"""
    user = update.effective_user
    
    # Только владелец может добавлять
    if user.id != OWNER_ID:
        await update.message.reply_text("⛔ Эта команда только для владельца бота.")
        return
    
    # Проверяем аргументы
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите ID пользователя.\n"
            "Пример: `/add_user 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        # Пробуем получить инфо о пользователе
        try:
            chat = await context.bot.get_chat(target_id)
            username = chat.username or ""
            first_name = chat.first_name or ""
        except:
            username = "unknown"
            first_name = "unknown"
        
        # Добавляем в БД
        if database.add_authorized_user(target_id, username, first_name, user.id):
            await update.message.reply_text(
                f"✅ Пользователь `{target_id}` добавлен в белый список.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"ℹ️ Пользователь `{target_id}` уже есть в белом списке.",
                parse_mode='Markdown'
            )
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет пользователя из белого списка (только для владельца)"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Эта команда только для владельца бота.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите ID пользователя.\n"
            "Пример: `/remove_user 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_id = int(context.args[0])
        
        if database.remove_authorized_user(target_id):
            await update.message.reply_text(
                f"✅ Пользователь `{target_id}` удалён из белого списка.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ Пользователь `{target_id}` не найден в белом списке.",
                parse_mode='Markdown'
            )
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список авторизованных пользователей"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Эта команда только для владельца бота.")
        return
    
    users = database.get_all_authorized()
    
    if not users:
        await update.message.reply_text("📭 Белый список пуст.")
        return
    
    text = "📋 **Авторизованные пользователи:**\n\n"
    for i, uid in enumerate(users, 1):
        text += f"{i}. `{uid}`\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

# ============== ОСНОВНАЯ ЛОГИКА БОТА ==============

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает обычные сообщения"""
    # Проверка авторизации
    if not await auth_check(update, context):
        return
    
    # Здесь будет логика сохранения сообщений
    # Пока просто логируем
    logger.info(f"Message from {update.effective_user.id}: {update.message.text}")

async def handle_deleted_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает удалённые сообщения"""
    # Проверка авторизации
    if not await auth_check(update, context):
        return
    
    # TODO: Здесь будет логика отслеживания удалений
    # Пока заглушка
    logger.info("Deleted messages detected!")

# ============== ЗАПУСК БОТА ==============

def main():
    """Запуск бота"""
    # Инициализируем БД
    database.init_db()
    
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("my_id", my_id))
    application.add_handler(CommandHandler("add_user", add_user))
    application.add_handler(CommandHandler("remove_user", remove_user))
    application.add_handler(CommandHandler("list_users", list_users))
    
    # Обработчик обычных сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем polling
    logger.info("Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()