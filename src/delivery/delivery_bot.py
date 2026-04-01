"""Delivery bot for sending qualified leads to operator."""

import asyncio
from datetime import datetime
from typing import Optional
import aiosqlite

from database import DATABASE_FILE


class QualifiedLead:
    """Qualified lead data."""
    
    def __init__(
        self,
        text: str,
        sender_id: int,
        sender_username: Optional[str],
        chat_id: int,
        chat_title: str,
        timestamp: datetime
    ):
        self.text = text
        self.sender_id = sender_id
        self.sender_username = sender_username
        self.chat_id = chat_id
        self.chat_title = chat_title
        self.timestamp = timestamp


class DeliveryBot:
    """Bot for delivering qualified leads to operator."""
    
    def __init__(self, bot_token: str, operator_chat_id: int):
        """
        Initialize delivery bot.
        
        Args:
            bot_token: Telegram bot token
            operator_chat_id: Operator's Telegram chat ID
        """
        self.bot_token = bot_token
        self.operator_chat_id = operator_chat_id
        self._bot = None
        self._app = None
    
    async def start(self) -> None:
        """Start the delivery bot."""
        try:
            from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.ext import Application, CallbackQueryHandler
            
            self._bot = Bot(token=self.bot_token)
            self._app = Application.builder().token(self.bot_token).build()
            
            # Register callback handlers
            self._app.add_handler(CallbackQueryHandler(
                self._handle_spam_callback,
                pattern=r'^spam:'
            ))
            self._app.add_handler(CallbackQueryHandler(
                self._handle_block_callback,
                pattern=r'^block:'
            ))
            
            # Start application
            await self._app.initialize()
            await self._app.start()
            
        except ImportError:
            raise ImportError("python-telegram-bot not installed. Run: pip install python-telegram-bot")

    
    async def stop(self) -> None:
        """Stop the delivery bot."""
        if self._app:
            await self._app.stop()
            await self._app.shutdown()
    
    async def deliver_lead(self, lead: QualifiedLead) -> None:
        """
        Deliver qualified lead to operator.
        
        Args:
            lead: Qualified lead to deliver
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        # Format sender link
        if lead.sender_username:
            sender_link = f"@{lead.sender_username}"
        else:
            sender_link = f"t.me/{lead.sender_id}"
        
        # Format message
        message_text = f"""🎯 Новый лид

💬 Текст:
{lead.text}

👤 Отправитель: {sender_link}
📍 Чат: {lead.chat_title}
🕐 Время: {lead.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # Create inline keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Спам", callback_data=f"spam:{lead.sender_id}:{lead.text[:50]}"),
                InlineKeyboardButton("В блок", callback_data=f"block:{lead.sender_id}:{lead.text[:50]}")
            ]
        ])
        
        # Send message
        await self._bot.send_message(
            chat_id=self.operator_chat_id,
            text=message_text,
            reply_markup=keyboard
        )

    
    async def _handle_spam_callback(self, update, context) -> None:
        """Handle spam button callback."""
        query = update.callback_query
        await query.answer()
        
        # Parse callback data
        parts = query.data.split(':', 2)
        if len(parts) < 3:
            return
        
        sender_id = parts[1]
        message_text = parts[2]
        
        # Get full message text from the callback message
        full_text = query.message.text
        # Extract the lead text (between "💬 Текст:" and "👤 Отправитель:")
        if "💬 Текст:" in full_text and "👤 Отправитель:" in full_text:
            start = full_text.index("💬 Текст:") + len("💬 Текст:")
            end = full_text.index("👤 Отправитель:")
            message_text = full_text[start:end].strip()
        
        # Save to spam database
        await self.handle_spam_feedback(message_text)
        
        # Send confirmation
        await query.edit_message_text(
            text=query.message.text + "\n\n✅ Добавлено в базу спама"
        )
    
    async def _handle_block_callback(self, update, context) -> None:
        """Handle block button callback."""
        query = update.callback_query
        await query.answer()
        
        # Parse callback data
        parts = query.data.split(':', 2)
        if len(parts) < 3:
            return
        
        sender_id = int(parts[1])
        message_text = parts[2]
        
        # Get full message text
        full_text = query.message.text
        if "💬 Текст:" in full_text and "👤 Отправитель:" in full_text:
            start = full_text.index("💬 Текст:") + len("💬 Текст:")
            end = full_text.index("👤 Отправитель:")
            message_text = full_text[start:end].strip()
        
        # Handle block feedback
        await self.handle_block_feedback(sender_id, message_text)
        
        # Send confirmation
        await query.edit_message_text(
            text=query.message.text + "\n\n✅ Отправитель заблокирован"
        )

    
    async def handle_spam_feedback(self, message_text: str) -> None:
        """
        Handle spam feedback from operator.
        
        Args:
            message_text: Message text to add to spam database
        """
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "INSERT INTO spam_database (message_text, created_at) VALUES (?, ?)",
                (message_text, datetime.now().isoformat())
            )
            await db.commit()
    
    async def handle_block_feedback(self, sender_id: int, message_text: str) -> None:
        """
        Handle block feedback from operator.
        
        Args:
            sender_id: Sender ID to block
            message_text: Message text to add to spam database
        """
        async with aiosqlite.connect(DATABASE_FILE) as db:
            # Add to blocklist
            await db.execute(
                "INSERT OR IGNORE INTO blocklist (user_id, created_at) VALUES (?, ?)",
                (sender_id, datetime.now().isoformat())
            )
            
            # Add to spam database
            await db.execute(
                "INSERT INTO spam_database (message_text, created_at) VALUES (?, ?)",
                (message_text, datetime.now().isoformat())
            )
            
            await db.commit()
