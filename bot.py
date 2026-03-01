import os
import logging
import threading
import sqlite3
from typing import Optional, Dict, Any

from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

import database

# ============== НАСТРОЙКИ ==============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
PORT = int(os.environ.get("PORT", 10000))  # Render даёт порт через переменную
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")  # Render даёт URL сервиса

# ============== FLASK-СЕРВЕР ДЛЯ HEALTH CHECKS ==============
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health():
    """Render пингует этот эндпоинт, чтобы сервис не засыпал"""
    return "Bot is running", 200

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram будет отправлять обновления сюда"""
    update = Update.de_json(request.get_json(force=True), bot)
    application.update_queue.put(update)
    return "OK", 200

def run_flask():
    """Запускает Flask в отдельном потоке"""
    flask_app.run(host='0.0.0.0', port=PORT)

# ============== ФУНКЦИЯ ПРОВЕРКИ АВТОРИЗАЦИИ ==============
async def is_authorized(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, есть ли пользователь в белом списке"""
    if user_id == OWNER_ID:
        return True
    
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
    if not await is_authorized(update.effective_user.id, update, context):
        return
    
    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        f"Я бот для отслеживания удалённых сообщений.\n\n"
        f"📋 Команды:\n"
        f"/add_user [ID] — добавить пользователя (только владелец)\n"
        f"/remove_user [ID] — удалить пользователя (только владелец)\n"
        f"/list_users — список авторизованных (только владелец)\n"
        f"/my_id — показать ваш Telegram ID"
    )

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ID пользователя"""
    if not await is_authorized(update.effective_user.id, update, context):
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
    
    if user.id != OWNER_ID:
        await update.message.reply_text("⛔ Эта команда только для владельца бота.")
        return
    
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
    if not await is_authorized(update.effective_user.id, update, context):
        return
    
    # TODO: Здесь будет сохранение сообщений для отслеживания удалений
    logger.info(f"Message from {update.effective_user.id}: {update.message.text}")

# ============== НАСТРОЙКА ВЕБХУКА ==============
async def setup_webhook(application: Application):
    """Устанавливает вебхук для бота"""
    if not WEBHOOK_URL:
        logger.error("RENDER_EXTERNAL_URL не установлен!")
        return
    
    webhook_url = f"{WEBHOOK_URL}/webhook"
    
    # Удаляем старый вебхук/поллинг
    await application.bot.delete_webhook(drop_pending_updates=True)
    
    # Устанавливаем новый вебхук
    await application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES
    )
    
    logger.info(f"Webhook установлен на {webhook_url}")

# ============== ЗАПУСК ==============
def main():
    """Главная функция запуска"""
    # Инициализируем БД
    database.init_db()

    # Запускаем Flask в отдельном потоке для health checks Render
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask server started on port {PORT} for health checks")

    # Создаём приложение Telegram
    application = Application.builder().token(TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("my_id", my_id))
    application.add_handler(CommandHandler("add_user", add_user))
    application.add_handler(CommandHandler("remove_user", remove_user))
    application.add_handler(CommandHandler("list_users", list_users))

    # Обработчик обычных сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота с вебхуками
    if not WEBHOOK_URL:
        logger.error("RENDER_EXTERNAL_URL не установлен! Переменная окружения обязательна.")
        return

    webhook_url = f"{WEBHOOK_URL}/webhook"
    logger.info(f"Запуск бота с вебхуком: {webhook_url}")

    # Запускаем бота в режиме вебхука (этот метод работает асинхронно и не блокирует поток)
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=webhook_url,
        secret_token=None,  # Можно добавить секретный токен для безопасности
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True  # Удалить старые обновления, накопившиеся пока бот не работал
    )

if __name__ == "__main__":
    main()