"""Admin notification system."""

from typing import Optional


class AdminNotifier:
    """Notifier for admin alerts."""
    
    def __init__(self, bot_token: str, admin_chat_id: int):
        """
        Initialize admin notifier.
        
        Args:
            bot_token: Telegram bot token
            admin_chat_id: Admin's Telegram chat ID
        """
        self.bot_token = bot_token
        self.admin_chat_id = admin_chat_id
        self._bot = None
    
    async def start(self) -> None:
        """Start the notifier."""
        try:
            from telegram import Bot
            self._bot = Bot(token=self.bot_token)
        except ImportError:
            raise ImportError("python-telegram-bot not installed")
    
    async def notify_userbot_status_change(
        self,
        userbot_id: int,
        old_status: str,
        new_status: str,
        reason: Optional[str] = None
    ) -> None:
        """
        Notify admin of userbot status change.
        
        Args:
            userbot_id: Userbot ID
            old_status: Previous status
            new_status: New status
            reason: Optional reason for change
        """
        if new_status not in ["banned", "unavailable"]:
            return  # Only notify for banned/unavailable
        
        emoji = "🚫" if new_status == "banned" else "⚠️"
        message = f"""{emoji} Изменение статуса юзербота

🤖 Userbot ID: {userbot_id}
📊 Старый статус: {old_status}
📊 Новый статус: {new_status}
"""
        
        if reason:
            message += f"💬 Причина: {reason}\n"
        
        await self._bot.send_message(
            chat_id=self.admin_chat_id,
            text=message
        )
