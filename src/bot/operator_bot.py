"""Operator bot interface for system management."""

from typing import Optional
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes


class OperatorBot:
    """Bot interface for operator commands."""
    
    def __init__(self, bot_token: str, operator_chat_id: int, ingestion_module):
        """
        Initialize operator bot.
        
        Args:
            bot_token: Telegram bot token
            operator_chat_id: Operator's chat ID
            ingestion_module: Reference to ingestion module
        """
        self.bot_token = bot_token
        self.operator_chat_id = operator_chat_id
        self.ingestion_module = ingestion_module
        self._app: Optional[Application] = None
    
    async def start(self) -> None:
        """Start the operator bot."""
        self._app = Application.builder().token(self.bot_token).build()
        
        # Register command handlers
        self._app.add_handler(CommandHandler("add_chats", self._handle_add_chats))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(CommandHandler("help", self._handle_help))
        
        # Start application
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
    
    async def stop(self) -> None:
        """Stop the operator bot."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
    
    async def _handle_add_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /add_chats command."""
        if update.effective_chat.id != self.operator_chat_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "Использование: /add_chats <ссылка1> <ссылка2> ...\n"
                "Пример: /add_chats t.me/chat1 @chat2"
            )
            return
        
        chat_links = context.args
        result = await self.ingestion_module.accept_chat_list(chat_links)
        
        await update.message.reply_text(
            f"✅ Обработано чатов: {len(result['valid'])}\n"
            f"❌ Невалидных: {len(result['invalid'])}\n"
            f"⏳ Добавлено в очередь вступлений"
        )

    
    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if update.effective_chat.id != self.operator_chat_id:
            return
        
        # Get system status from database
        import aiosqlite
        from database import DATABASE_FILE
        
        async with aiosqlite.connect(DATABASE_FILE) as db:
            # Active userbots
            cursor = await db.execute("SELECT COUNT(*) FROM userbots WHERE status='active'")
            active_userbots = (await cursor.fetchone())[0]
            
            # Active chats
            cursor = await db.execute("SELECT COUNT(*) FROM chats WHERE status='active'")
            active_chats = (await cursor.fetchone())[0]
            
            # Pending join tasks
            cursor = await db.execute("SELECT COUNT(*) FROM join_tasks WHERE status='pending'")
            pending_tasks = (await cursor.fetchone())[0]
        
        status_message = f"""📊 Статус системы

🤖 Активные юзерботы: {active_userbots}
💬 Чаты в мониторинге: {active_chats}
⏳ Задач в очереди: {pending_tasks}
"""
        
        await update.message.reply_text(status_message)
    
    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if update.effective_chat.id != self.operator_chat_id:
            return
        
        help_text = """🤖 Доступные команды:

/add_chats <ссылки> - Добавить чаты для мониторинга
/status - Показать статус системы
/help - Показать эту справку
"""
        
        await update.message.reply_text(help_text)
