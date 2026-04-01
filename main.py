"""Main entry point for Telegram Lead Monitoring System."""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from database import init_database
from src.ingestion.ingestion_module import IngestionModule
from src.ingestion.join_queue import JoinQueue
from src.userbot.userbot_pool_manager import UserbotPoolManager
from src.parser.message_parser import MessageParser
from src.verifier.llm_verifier import LLMVerifier
from src.delivery.delivery_bot import DeliveryBot, QualifiedLead
from src.bot.operator_bot import OperatorBot
from src.logging.activity_logger import ActivityLogger
from src.notifications.admin_notifier import AdminNotifier


class SystemManager:
    """Main system manager."""
    
    def __init__(self):
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._accepting_tasks = True
        
        # Components
        self.userbot_pool: Optional[UserbotPoolManager] = None
        self.join_queue: Optional[JoinQueue] = None
        self.ingestion: Optional[IngestionModule] = None
        self.message_parser: Optional[MessageParser] = None
        self.llm_verifier: Optional[LLMVerifier] = None
        self.delivery_bot: Optional[DeliveryBot] = None
        self.operator_bot: Optional[OperatorBot] = None
        self.admin_notifier: Optional[AdminNotifier] = None
    
    def setup_signal_handlers(self):
        """Setup graceful shutdown handlers."""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal."""
        print(f"\nReceived signal {signum}, initiating graceful shutdown...")
        self._accepting_tasks = False
        self._shutdown_event.set()
    
    def is_accepting_tasks(self) -> bool:
        """Check if system is accepting new tasks."""
        return self._accepting_tasks
    
    async def run(self):
        """Run the system."""
        print("=" * 50)
        print("Telegram Lead Monitoring System")
        print("=" * 50)
        print()
        
        # Initialize database
        print("Initializing database...")
        await init_database()
        print("✓ Database initialized")
        
        # Load configuration
        print("Loading configuration...")
        print(f"✓ Loaded {len(config._data)} configuration parameters")
        print(f"  - Trigger words: {len(config['trigger_words'])}")
        print(f"  - LLM provider: {config['llm_provider']}")
        print(f"  - Join delay: {config['join_delay_min']}-{config['join_delay_max']}s")
        print(f"  - Daily join limit: {config['daily_join_limit']}")
        print()
        
        # Initialize components
        print("Initializing components...")
        await self._initialize_components()
        print("✓ All components initialized")
        print()
        
        print("System is ready!")
        print("Press Ctrl+C to stop")
        print()
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        print("\nShutting down gracefully...")
        print("Stopping new task acceptance...")
        
        # Stop components
        await self._stop_components()
        
        # Wait for active tasks to complete (30s timeout)
        if self._tasks:
            print(f"Waiting for {len(self._tasks)} active tasks to complete (30s timeout)...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks, return_exceptions=True),
                    timeout=30.0
                )
                print("✓ All tasks completed")
            except asyncio.TimeoutError:
                print("⚠ Timeout reached, forcing shutdown...")
                for task in self._tasks:
                    if not task.done():
                        task.cancel()
        
        # Save state
        await self._save_state()
        print("✓ State saved")
        print("✓ Shutdown complete")
    
    async def _save_state(self) -> None:
        """Save system state before shutdown."""
        # State is already persisted in database by individual components
        # This is a placeholder for any additional state saving logic
        pass
    
    async def _load_userbot_sessions(self) -> None:
        """Load userbot sessions from sessions/ directory."""
        sessions_dir = Path("sessions")
        
        if not sessions_dir.exists():
            print("  ⚠ sessions/ directory not found, creating it...")
            sessions_dir.mkdir(exist_ok=True)
            print("  ℹ Place your .session files in sessions/ directory")
            return
        
        session_files = list(sessions_dir.glob("*.session"))
        
        if not session_files:
            print("  ⚠ No .session files found in sessions/ directory")
            print("  ℹ Run get_code.bat to create session files")
            return
        
        print(f"  - Found {len(session_files)} session file(s)")
        
        for session_file in session_files:
            try:
                session_name = session_file.stem  # filename without extension
                userbot_id = await self.userbot_pool.add_userbot(str(session_file))
                print(f"    ✓ Loaded {session_name} (ID: {userbot_id})")
            except Exception as e:
                print(f"    ✗ Failed to load {session_file.name}: {e}")
    
    async def _initialize_components(self) -> None:
        """Initialize all system components."""
        # Initialize userbot pool
        self.userbot_pool = UserbotPoolManager(
            health_check_interval=config['health_check_interval']
        )
        
        # Initialize join queue
        self.join_queue = JoinQueue()
        
        # Initialize LLM verifier
        self.llm_verifier = LLMVerifier(
            provider=config['llm_provider'],
            api_key=config.get('llm_api_key', ''),
            model=config.get('llm_model'),
            max_concurrent=config['llm_max_concurrent'],
            timeout=config['llm_timeout'],
            max_retries=config['llm_max_retries'],
            max_spam_examples=config['max_spam_examples'],
            spam_cache_update_interval=config['spam_cache_update_interval']
        )
        
        # Initialize delivery bot
        self.delivery_bot = DeliveryBot(
            bot_token=config.get('bot_token', ''),
            operator_chat_id=config.get('operator_chat_id', 0)
        )
        
        # Initialize message parser with callback
        async def on_qualified_lead(message):
            """Callback for qualified leads."""
            lead = QualifiedLead(
                text=message.text,
                sender_id=message.sender_id,
                sender_username=message.sender_username,
                chat_id=message.chat_id,
                chat_title=message.chat_title,
                timestamp=message.timestamp
            )
            await self.delivery_bot.deliver_lead(lead)
            await ActivityLogger.log_lead_delivery(
                sender_id=message.sender_id,
                chat_title=message.chat_title,
                message_preview=message.text[:100]
            )
        
        async def on_message(message):
            """Callback for parsed messages."""
            # Verify with LLM
            is_qualified = await self.llm_verifier.verify_lead(message.text)
            if is_qualified:
                await on_qualified_lead(message)
        
        self.message_parser = MessageParser(
            trigger_words=config['trigger_words'],
            on_message_callback=on_message
        )
        
        # Initialize ingestion module
        self.ingestion = IngestionModule(
            join_delay_min=config['join_delay_min'],
            join_delay_max=config['join_delay_max'],
            daily_join_limit=config['daily_join_limit']
        )
        
        # Initialize admin notifier
        if config.get('admin_chat_id'):
            self.admin_notifier = AdminNotifier(
                bot_token=config.get('bot_token', ''),
                admin_chat_id=config['admin_chat_id']
            )
            await self.admin_notifier.start()
        
        # Initialize operator bot
        if config.get('operator_chat_id'):
            self.operator_bot = OperatorBot(
                bot_token=config.get('bot_token', ''),
                operator_chat_id=config['operator_chat_id'],
                ingestion_module=self.ingestion
            )
            await self.operator_bot.start()
        
        # Start background tasks
        await self.delivery_bot.start()
        await self.llm_verifier.start_spam_cache_update()
        await self.message_parser.start_cleanup_task()
        
        # Cleanup old pending tasks before loading
        cleaned_tasks = await self.join_queue.cleanup_old_tasks()
        if cleaned_tasks > 0:
            print(f"  - Marked {cleaned_tasks} old pending tasks as failed")
        
        # Load pending join tasks from database
        loaded_tasks = await self.join_queue.load_pending_tasks()
        if loaded_tasks > 0:
            print(f"  - Loaded {loaded_tasks} pending join tasks")
        
        # Load userbot sessions from sessions/ directory
        await self._load_userbot_sessions()
        
        # Start background tasks
        self._tasks.append(asyncio.create_task(self._process_join_queue()))
        self._tasks.append(asyncio.create_task(self._process_pending_chats()))
    
    async def _stop_components(self) -> None:
        """Stop all system components."""
        if self.join_queue:
            self.join_queue.stop()
        
        if self.operator_bot:
            await self.operator_bot.stop()
        
        if self.delivery_bot:
            await self.delivery_bot.stop()
        
        if self.llm_verifier:
            await self.llm_verifier.stop_spam_cache_update()
        
        if self.message_parser:
            await self.message_parser.stop_cleanup_task()
    
    async def _process_join_queue(self) -> None:
        """Process join queue tasks."""
        from src.ingestion.join_logic import JoinLogic
        
        join_logic = JoinLogic(self.userbot_pool)
        
        while not self._shutdown_event.is_set():
            task = await self.join_queue.get_next_task()
            
            if task is None:
                # Queue stopped
                break
            
            # Mark as processing
            await self.join_queue.mark_task_processing(task.task_id)
            
            await ActivityLogger.log(
                component="JoinQueue",
                level="INFO",
                message="Starting join task execution",
                metadata={
                    "task_id": task.task_id,
                    "userbot_id": task.userbot_id,
                    "chat_id": task.chat_id,
                    "scheduled_at": task.scheduled_at.isoformat()
                }
            )
            
            try:
                # Execute join
                success = await join_logic.execute_join(task.userbot_id, task.chat_id)
                
                if success:
                    await self.join_queue.mark_task_completed(task.task_id)
                    await ActivityLogger.log(
                        component="JoinQueue",
                        level="INFO",
                        message="Join task completed successfully",
                        metadata={
                            "task_id": task.task_id,
                            "userbot_id": task.userbot_id,
                            "chat_id": task.chat_id
                        }
                    )
                else:
                    await self.join_queue.mark_task_failed(task.task_id)
                    await ActivityLogger.log(
                        component="JoinQueue",
                        level="WARNING",
                        message="Join task failed",
                        metadata={
                            "task_id": task.task_id,
                            "userbot_id": task.userbot_id,
                            "chat_id": task.chat_id
                        }
                    )
            
            except Exception as e:
                print(f"Error processing join task {task.task_id}: {e}")
                await ActivityLogger.log_error(
                    component="JoinQueue",
                    error_message=f"Exception while processing join task {task.task_id}",
                    exception=e
                )
                await self.join_queue.mark_task_failed(task.task_id)
    
    async def _process_pending_chats(self) -> None:
        """Process pending chats and create join tasks."""
        import aiosqlite
        
        while not self._shutdown_event.is_set():
            try:
                # Check for pending chats every 30 seconds
                await asyncio.sleep(30)
                
                async with aiosqlite.connect("telegram_leads.db") as db:
                    # Get pending chats WITHOUT existing pending tasks
                    # LEFT JOIN prevents duplicate task creation by excluding chats
                    # that already have a pending task in the join_tasks table
                    cursor = await db.execute("""
                        SELECT c.id FROM chats c
                        LEFT JOIN join_tasks jt ON c.id = jt.chat_id AND jt.status = 'pending'
                        WHERE c.status = 'pending' 
                        AND c.assigned_userbot_id IS NULL
                        AND jt.id IS NULL
                    """)
                    pending_chats = await cursor.fetchall()
                    
                    if not pending_chats:
                        continue
                    
                    chat_ids = [row[0] for row in pending_chats]
                    print(f"Found {len(chat_ids)} pending chat(s), creating join tasks...")
                    
                    await ActivityLogger.log(
                        component="IngestionModule",
                        level="INFO",
                        message="Found pending chats - creating join tasks",
                        metadata={
                            "pending_chats_count": len(chat_ids),
                            "chat_ids": chat_ids
                        }
                    )
                    
                    # Distribute chats among userbots
                    try:
                        distribution = await self.ingestion.distribute_chats(chat_ids)
                        
                        # Create join tasks in database
                        await self.ingestion.enqueue_join_tasks(distribution)
                        
                        # Add newly created tasks to the queue
                        from datetime import datetime, timezone
                        tasks_added = 0
                        
                        async with aiosqlite.connect("telegram_leads.db") as db2:
                            for userbot_id, assigned_chat_ids in distribution.items():
                                for chat_id in assigned_chat_ids:
                                    # Get the task we just created
                                    cursor2 = await db2.execute("""
                                        SELECT id, scheduled_at
                                        FROM join_tasks
                                        WHERE userbot_id = ? AND chat_id = ? AND status = 'pending'
                                        ORDER BY created_at DESC
                                        LIMIT 1
                                    """, (userbot_id, chat_id))
                                    task_row = await cursor2.fetchone()
                                    
                                    if task_row:
                                        task_id, scheduled_at_str = task_row
                                        scheduled_at = datetime.fromisoformat(scheduled_at_str)
                                        # Ensure timezone-aware datetime
                                        if scheduled_at.tzinfo is None:
                                            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
                                        await self.join_queue.add_task(task_id, userbot_id, chat_id, scheduled_at)
                                        tasks_added += 1
                        
                        print(f"✓ Created join tasks for {len(chat_ids)} chat(s)")
                        print(f"✓ Добавлено {tasks_added} задач в очередь выполнения")
                        
                        await ActivityLogger.log(
                            component="IngestionModule",
                            level="INFO",
                            message="Join tasks created and enqueued successfully",
                            metadata={
                                "chats_processed": len(chat_ids),
                                "tasks_added_to_queue": tasks_added,
                                "distribution": {str(k): len(v) for k, v in distribution.items()}
                            }
                        )
                    
                    except ValueError as e:
                        print(f"⚠ Cannot create join tasks: {e}")
                        await ActivityLogger.log(
                            component="IngestionModule",
                            level="WARNING",
                            message="Cannot create join tasks",
                            metadata={
                                "error": str(e),
                                "pending_chats_count": len(chat_ids)
                            }
                        )
                        # Will retry on next iteration
            
            except Exception as e:
                print(f"Error in pending chats processor: {e}")
                await ActivityLogger.log_error(
                    component="IngestionModule",
                    error_message="Error in pending chats processor",
                    exception=e
                )


async def main():
    """Main entry point."""
    manager = SystemManager()
    manager.setup_signal_handlers()
    await manager.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
