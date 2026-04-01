# Документ Дизайна: Система Асинхронного Мониторинга Telegram-Чатов

## Overview

Система представляет собой асинхронный многокомпонентный сервис для автоматизированного перехвата и квалификации лидов из Telegram-чатов. Архитектура построена на принципах event-driven design с использованием asyncio для обеспечения высокой пропускной способности при минимальном потреблении ресурсов.

Ключевые архитектурные решения:
- Полностью асинхронная обработка на базе asyncio (Python 3.11+)
- Пул юзерботов с балансировкой нагрузки для имитации человеческого поведения
- Двухуровневая фильтрация: триггерные слова → LLM-верификация
- Few-shot learning для LLM с динамическим обновлением негативных примеров
- Режим абсолютной невидимости (no read receipts, no online status)
- Дедупликация на основе нормализованного текста с TTL 24 часа

Технологический стек:
- Python 3.11+ (asyncio, aiohttp)
- Pyrogram (асинхронный Telegram MTProto API клиент)
- SQLite с WAL mode (один локальный файл `.db`, нулевая настройка)
- asyncio.Queue для внутренних очередей задач
- Claude Haiku / GPT-4o-mini для LLM-верификации

Развертывание:
- Windows VDS сервер
- Стандартный Python venv и requirements.txt
- Установка и запуск через start.bat (один клик)
- Web Dashboard на Streamlit (start_dashboard.bat, localhost:8501)
- Фоновая работа 24/7 через NSSM или Task Scheduler

## Architecture

### Компонентная Архитектура

Система состоит из 7 основных компонентов:

```
┌─────────────────────────────────────────────────────────────┐
│                   Web Dashboard (Streamlit)                  │
│              localhost:8501 - Configuration UI               │
│   - Trigger words editor    - API keys management           │
│   - Join delays sliders     - System status dashboard       │
│   - Userbot management      - Leads statistics              │
└────────────────┬────────────────────────────────────────────┘
                 │ (reads/writes config.json)
                 │
┌────────────────┴────────────────────────────┬────────────────┐
│                      Operator Interface      │                │
│                    (Telegram Bot API)        │                │
└────────────────┬────────────────────────────┬────────────────┘
                 │                            │
                 ▼                            ▼
┌────────────────────────────┐  ┌────────────────────────────┐
│   Ingestion Module         │  │   Delivery Bot             │
│   - Chat list validation   │  │   - Lead delivery          │
│   - Userbot distribution   │  │   - Spam feedback          │
│   - Join queue management  │  │   - Block list management  │
└────────────┬───────────────┘  └────────────▲───────────────┘
             │                               │
             ▼                               │
┌────────────────────────────┐              │
│   Join Queue               │              │
│   (asyncio.Queue)          │              │
│   - Randomized delays      │              │
│   - 300-1800s intervals    │              │
└────────────┬───────────────┘              │
             │                               │
             ▼                               │
┌────────────────────────────┐              │
│   Userbot Pool Manager     │              │
│   - Session management     │              │
│   - Health monitoring      │              │
│   - FloodWait handling     │              │
│   - 10 joins/day limit     │              │
└────────────┬───────────────┘              │
             │                               │
             ▼                               │
┌────────────────────────────┐              │
│   Message Parser           │              │
│   - Real-time streaming    │              │
│   - Trigger word filter    │              │
│   - Deduplication (24h)    │              │
│   - Invisible mode         │              │
└────────────┬───────────────┘              │
             │                               │
             ▼                               │
┌────────────────────────────┐              │
│   LLM Verifier             │              │
│   - Few-shot prompting     │              │
│   - Concurrency limit: 10  │              │
│   - Retry with backoff     │              │
│   - Spam DB integration    │              │
└────────────────────────────┴──────────────┘
```

### Поток Данных

1. **Configuration Flow**: Web Dashboard → config.json → System Components (hot reload)
2. **Ingestion Flow**: Operator → Ingestion Module → Join Queue → Userbot Pool → Telegram API
3. **Monitoring Flow**: Telegram API → Message Parser → Trigger Filter → LLM Verifier → Delivery Bot → Operator
4. **Feedback Loop**: Operator → Delivery Bot → Spam Database → LLM Verifier (prompt update)
5. **Statistics Flow**: SQLite Database → Web Dashboard (real-time metrics)

### Асинхронная Модель Выполнения

Все компоненты работают как независимые asyncio tasks:

```python
# Концептуальная структура
async def main():
    async with asyncio.TaskGroup() as tg:
        tg.create_task(ingestion_service())
        tg.create_task(join_queue_processor())
        tg.create_task(message_parser_service())
        tg.create_task(llm_verifier_service())
        tg.create_task(delivery_bot_service())
        tg.create_task(health_monitor_service())
        tg.create_task(config_watcher_service())  # Hot reload config.json
```

## Components and Interfaces

### 1. Ingestion Module

**Ответственность**: Прием списков чатов, валидация, распределение между юзерботами, управление очередью вступлений.

**Интерфейс**:
```python
class IngestionModule:
    async def accept_chat_list(self, chat_links: list[str]) -> ValidationResult
    async def validate_chat_link(self, link: str) -> bool
    async def distribute_chats(self, chats: list[Chat]) -> dict[UserbotId, list[Chat]]
    async def enqueue_join_task(self, userbot_id: UserbotId, chat: Chat) -> None
```

**Логика распределения**:
- Round-robin с учетом текущей нагрузки (количество активных чатов)
- Проверка дневного лимита (10 вступлений/сутки на юзербота)
- Исключение недоступных/заблокированных юзерботов

**Валидация ссылок**:
- Regex: `^(https?://)?(t\.me/|@)[\w\d_]+$`
- Проверка на дубликаты в базе данных

### 2. Join Queue (asyncio.Queue)

**Ответственность**: Асинхронная очередь задач вступления с рандомизированными задержками.

**Интерфейс**:
```python
class JoinQueue:
    def __init__(self):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
    
    async def add_task(self, userbot_id: UserbotId, chat: Chat) -> None
    async def process_tasks(self) -> None  # Бесконечный цикл обработки
```

**Механика задержек**:
- При добавлении задачи: `scheduled_time = now() + random.randint(300, 1800)`
- PriorityQueue сортирует по `scheduled_time`
- Процессор ждет до `scheduled_time` перед выполнением: `await asyncio.sleep(delay)`

**Персистентность**:
- Задачи сохраняются в БД при добавлении
- При запуске системы незавершенные задачи загружаются обратно в очередь

### 3. Userbot Pool Manager

**Ответственность**: Управление пулом юзерботов, мониторинг здоровья, обработка FloodWait.

**Интерфейс**:
```python
class UserbotPoolManager:
    async def add_userbot(self, session_file: str) -> UserbotId
    async def remove_userbot(self, userbot_id: UserbotId) -> None
    async def get_available_userbots(self) -> list[Userbot]
    async def mark_unavailable(self, userbot_id: UserbotId, reason: str, duration: int) -> None
    async def health_check_loop(self) -> None  # Каждые 300 секунд
```

**Состояния юзербота**:
- `active`: Доступен для задач
- `unavailable`: Временно недоступен (FloodWait)
- `banned`: Заблокирован Telegram
- `inactive`: Деактивирован администратором

**FloodWait обработка**:
```python
try:
    await userbot.join_chat(chat_link)
except FloodWait as e:
    await pool_manager.mark_unavailable(userbot.id, "floodwait", e.value)
    # Задача перераспределяется на другого юзербота
```

**Лимиты**:
- 10 вступлений в сутки на юзербота (счетчик сбрасывается в 00:00 UTC)
- 20 API запросов в секунду на юзербота (rate limiter на базе token bucket)

### 4. Message Parser

**Ответственность**: Подписка на сообщения из активных чатов, фильтрация по триггерным словам, дедупликация.

**Интерфейс**:
```python
class MessageParser:
    async def subscribe_to_chat(self, chat_id: int, userbot: Userbot) -> None
    async def handle_new_message(self, message: Message) -> None
    async def check_trigger_words(self, text: str) -> bool
    async def deduplicate(self, message: Message) -> bool
```

**Режим невидимости** (Pyrogram):
```python
app = Client(
    "userbot_session",
    no_updates=False,  # Получаем обновления
    sleep_threshold=0,  # Не отправляем статус "онлайн"
)

@app.on_message(filters.chat(monitored_chats))
async def message_handler(client, message):
    # Обработка без отправки read receipts
    # Pyrogram по умолчанию не отправляет read receipts при использовании handlers
    pass
```

**Дедупликация**:
```python
def normalize_text(text: str) -> str:
    """Удаляет спецсимволы, эмодзи, ссылки, пробелы для хэширования"""
    # Удаление URL
    text = re.sub(r'http[s]?://\S+', '', text)
    # Удаление эмодзи
    text = emoji.replace_emoji(text, '')
    # Удаление спецсимволов и пробелов
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', '', text)
    return text.lower()

async def deduplicate(self, message: Message) -> bool:
    normalized = normalize_text(message.text)
    msg_hash = hashlib.sha256(normalized.encode()).hexdigest()
    
    # Проверка в БД: существует ли хэш с timestamp < 24h
    existing = await db.get_message_hash(msg_hash)
    if existing and (now() - existing.timestamp) < timedelta(hours=24):
        return True  # Дубликат
    
    await db.save_message_hash(msg_hash, now())
    return False  # Уникальное сообщение
```

**Триггерные слова**:
- Загружаются из конфигурации: `["ищу", "нужен", "заказ", "разработчик", "программист", ...]`
- Проверка без учета регистра: `any(trigger.lower() in text.lower() for trigger in triggers)`

### 5. LLM Verifier

**Ответственность**: Квалификация лидов через LLM с few-shot learning, управление concurrency, retry logic.

**Интерфейс**:
```python
class LLMVerifier:
    def __init__(self, max_concurrent: int = 10):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._spam_cache: list[str] = []
        self._cache_update_task = asyncio.create_task(self._update_spam_cache())
    
    async def verify_lead(self, message: Message) -> bool
    async def _build_prompt(self, message_text: str) -> str
    async def _update_spam_cache(self) -> None  # Каждые 60 секунд
    async def _call_llm_api(self, prompt: str) -> str
```

**Concurrency Control**:
```python
async def verify_lead(self, message: Message) -> bool:
    async with self._semaphore:  # Максимум 10 одновременных запросов
        for attempt in range(3):
            try:
                prompt = await self._build_prompt(message.text)
                response = await self._call_llm_api(prompt)
                return self._parse_response(response)
            except RateLimitError:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        return False  # После 3 неудачных попыток считаем не лидом
```

**Few-Shot Prompt Structure**:
```python
async def _build_prompt(self, message_text: str) -> str:
    negative_examples = self._spam_cache[:20]  # Последние 20 из БД
    
    system_prompt = """Ты классификатор лидов для IT-услуг.
    
ЗАДАЧА: Определи, является ли сообщение реальным запросом на услуги разработки/дизайна.

КРИТЕРИИ РЕАЛЬНОГО ЗАПРОСА:
- Явное указание на потребность в услуге
- Описание задачи или проекта
- Вопросы о стоимости/сроках
- Поиск исполнителя

НЕ ЯВЛЯЕТСЯ ЗАПРОСОМ:
- Реклама услуг
- Предложения работы
- Общие обсуждения
- Спам и флуд

ПРИМЕРЫ СПАМА (НЕ лиды):
"""
    for i, spam_example in enumerate(negative_examples, 1):
        system_prompt += f"\n{i}. \"{spam_example}\""
    
    system_prompt += f"""

СООБЩЕНИЕ ДЛЯ АНАЛИЗА:
"{message_text}"

ОТВЕТ (только "ДА" или "НЕТ"):"""
    
    return system_prompt
```

**API Integration**:
- Claude Haiku: `anthropic.AsyncAnthropic().messages.create()`
- GPT-4o-mini: `openai.AsyncOpenAI().chat.completions.create()`
- Timeout: 30 секунд на запрос

### 6. Web Dashboard

**Ответственность**: Веб-интерфейс для управления настройками системы и мониторинга статуса.

**Технология**: Streamlit (Python-нативный UI фреймворк)

**Интерфейс**:
```python
# dashboard.py - Streamlit приложение
import streamlit as st
import json
from pathlib import Path

def load_config() -> dict:
    """Загрузка config.json"""
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config: dict) -> None:
    """Сохранение config.json"""
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
```

**Функциональные блоки**:

1. **Настройки триггерных слов**:
```python
st.subheader("🔍 Триггерные слова")
trigger_words = st.text_area(
    "Введите триггерные слова (по одному на строку)",
    value="\n".join(config["trigger_words"]),
    height=200
)
if st.button("Сохранить триггерные слова"):
    config["trigger_words"] = [w.strip() for w in trigger_words.split("\n") if w.strip()]
    save_config(config)
    st.success("✅ Сохранено")
```

2. **API ключи**:
```python
st.subheader("🔑 API Ключи")
config["llm_provider"] = st.selectbox("LLM Provider", ["claude", "openai"])
config["llm_api_key"] = st.text_input("API Key", value=config.get("llm_api_key", ""), type="password")
config["telegram_api_id"] = st.text_input("Telegram API ID", value=config.get("telegram_api_id", ""))
config["telegram_api_hash"] = st.text_input("Telegram API Hash", value=config.get("telegram_api_hash", ""), type="password")
config["bot_token"] = st.text_input("Bot Token", value=config.get("bot_token", ""), type="password")
```

3. **Настройки задержек**:
```python
st.subheader("⏱️ Параметры очереди вступлений")
min_delay, max_delay = st.slider(
    "Диапазон задержек между вступлениями (секунды)",
    min_value=60,
    max_value=3600,
    value=(config.get("join_delay_min", 300), config.get("join_delay_max", 1800))
)
config["join_delay_min"] = min_delay
config["join_delay_max"] = max_delay

config["daily_join_limit"] = st.number_input(
    "Лимит вступлений в сутки на один юзербот",
    min_value=1,
    max_value=50,
    value=config.get("daily_join_limit", 10)
)
```

4. **Дашборд статуса**:
```python
st.subheader("📊 Статус системы")

# Подключение к БД для получения статистики
import aiosqlite
import asyncio

async def get_stats():
    async with aiosqlite.connect("telegram_leads.db") as db:
        # Количество активных юзерботов
        cursor = await db.execute("SELECT COUNT(*) FROM userbots WHERE status='active'")
        active_userbots = (await cursor.fetchone())[0]
        
        # Количество чатов в мониторинге
        cursor = await db.execute("SELECT COUNT(*) FROM chats WHERE status='active'")
        active_chats = (await cursor.fetchone())[0]
        
        # Количество лидов за сегодня
        cursor = await db.execute("""
            SELECT COUNT(*) FROM activity_logs 
            WHERE component='DeliveryBot' 
            AND DATE(created_at) = DATE('now')
        """)
        leads_today = (await cursor.fetchone())[0]
        
        return active_userbots, active_chats, leads_today

stats = asyncio.run(get_stats())

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("🤖 Активные юзерботы", stats[0])
with col2:
    st.metric("💬 Чаты в мониторинге", stats[1])
with col3:
    st.metric("🎯 Лиды сегодня", stats[2])
```

**Дизайн**:
- Dark mode по умолчанию
- Современный минималистичный интерфейс
- Responsive layout
- Автообновление статистики каждые 5 секунд

**Запуск**: Отдельный скрипт `start_dashboard.bat`:
```batch
@echo off
call venv\Scripts\activate
streamlit run dashboard.py --server.port 8501 --server.address localhost
```

**Интеграция с основной системой**:
- Dashboard читает/пишет `config.json`
- Основная система (main.py) читает `config.json` при запуске и перезагружает при изменении файла
- Изменения в config.json применяются без перезапуска основной системы (hot reload)

### 7. Delivery Bot

**Ответственность**: Доставка квалифицированных лидов оператору, обработка обратной связи (спам/блок).

**Интерфейс**:
```python
class DeliveryBot:
    async def deliver_lead(self, lead: QualifiedLead) -> None
    async def handle_spam_feedback(self, message_id: int, message_text: str) -> None
    async def handle_block_feedback(self, message_id: int, sender_id: int, message_text: str) -> None
```

**Формат сообщения**:
```
🎯 Новый лид

💬 Текст:
{message_text}

👤 Отправитель: @{username} или t.me/{user_id}
📍 Чат: {chat_title}
🕐 Время: {timestamp}

[Кнопка: Спам] [Кнопка: В блок]
```

**Обработка обратной связи**:
```python
@bot.callback_query_handler(func=lambda call: call.data.startswith("spam:"))
async def handle_spam(call):
    message_text = extract_text_from_message(call.message)
    await db.add_to_spam_database(message_text, timestamp=now())
    await bot.answer_callback_query(call.id, "✅ Добавлено в базу спама")

@bot.callback_query_handler(func=lambda call: call.data.startswith("block:"))
async def handle_block(call):
    sender_id, message_text = extract_data(call.message)
    await db.add_to_blocklist(sender_id)
    await db.add_to_spam_database(message_text, timestamp=now())
    await bot.answer_callback_query(call.id, "✅ Отправитель заблокирован")
```

## Data Models

### Database Schema (SQLite)

**Файл базы данных**: `telegram_leads.db` (создается автоматически при первом запуске)

**WAL Mode**: Включается автоматически для улучшения производительности при конкурентном доступе

```sql
-- Таблица юзерботов
CREATE TABLE userbots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_file TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('active', 'unavailable', 'banned', 'inactive')),
    unavailable_until TIMESTAMP NULL,
    joins_today INTEGER DEFAULT 0,
    joins_reset_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица чатов
CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_link TEXT NOT NULL UNIQUE,
    chat_id BIGINT NULL,  -- Telegram chat ID после вступления
    chat_title TEXT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'active', 'error', 'awaiting_approval', 'manual_required')),
    assigned_userbot_id INTEGER NULL REFERENCES userbots(id),
    error_message TEXT NULL,
    joined_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица задач вступления
CREATE TABLE join_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userbot_id INTEGER NOT NULL REFERENCES userbots(id),
    chat_id INTEGER NOT NULL REFERENCES chats(id),
    scheduled_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL
);

-- Таблица хэшей сообщений для дедупликации
CREATE TABLE message_hashes (
    hash TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL
);

-- Индекс для очистки старых хэшей
CREATE INDEX idx_message_hashes_created_at ON message_hashes(created_at);

-- Таблица базы спама
CREATE TABLE spam_database (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индекс для быстрого получения последних примеров
CREATE INDEX idx_spam_created_at ON spam_database(created_at DESC);

-- Таблица заблокированных отправителей
CREATE TABLE blocklist (
    user_id BIGINT PRIMARY KEY,
    username TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица логов активности
CREATE TABLE activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT NOT NULL,
    level TEXT NOT NULL CHECK(level IN ('INFO', 'WARNING', 'ERROR')),
    message TEXT NOT NULL,
    metadata JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_logs_component_created ON activity_logs(component, created_at);
```

### Python Data Models

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class UserbotStatus(Enum):
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    BANNED = "banned"
    INACTIVE = "inactive"

@dataclass
class Userbot:
    id: int
    session_file: str
    status: UserbotStatus
    unavailable_until: datetime | None
    joins_today: int
    joins_reset_at: datetime

class ChatStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    AWAITING_APPROVAL = "awaiting_approval"
    MANUAL_REQUIRED = "manual_required"

@dataclass
class Chat:
    id: int
    chat_link: str
    chat_id: int | None
    chat_title: str | None
    status: ChatStatus
    assigned_userbot_id: int | None
    error_message: str | None
    joined_at: datetime | None

@dataclass
class JoinTask:
    id: int
    userbot_id: int
    chat_id: int
    scheduled_at: datetime
    status: str  # pending, processing, completed, failed

@dataclass
class Message:
    text: str
    sender_id: int
    sender_username: str | None
    chat_id: int
    chat_title: str
    timestamp: datetime

@dataclass
class QualifiedLead:
    message: Message
    verified_at: datetime
```

## Error Handling

### FloodWait Handling

```python
from pyrogram.errors import FloodWait

async def safe_join_chat(userbot: Userbot, chat_link: str) -> tuple[bool, str | None]:
    try:
        await userbot.client.join_chat(chat_link)
        return True, None
    except FloodWait as e:
        # Приостановить юзербота на e.value секунд
        await pool_manager.mark_unavailable(
            userbot.id, 
            reason="floodwait", 
            duration=e.value
        )
        # Перераспределить задачу
        await join_queue.redistribute_task(userbot.id, chat_link)
        return False, f"FloodWait: {e.value}s"
    except Exception as e:
        logger.error(f"Join failed: {e}", exc_info=True)
        return False, str(e)
```

### LLM API Error Handling

```python
async def verify_with_retry(self, message: Message) -> bool:
    for attempt in range(3):
        try:
            async with self._semaphore:
                response = await self._call_llm_api(message.text)
                return self._parse_response(response)
        except RateLimitError as e:
            if attempt == 2:
                logger.error(f"LLM rate limit after 3 attempts: {e}")
                return False
            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
        except TimeoutError:
            logger.warning(f"LLM timeout on attempt {attempt + 1}")
            if attempt == 2:
                return False
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"LLM API error: {e}", exc_info=True)
            return False
    return False
```

### Database Error Handling

```python
import aiosqlite

async def init_database():
    """Инициализация SQLite с WAL mode"""
    async with aiosqlite.connect("telegram_leads.db") as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.commit()

async def save_with_retry(operation: Callable, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            async with aiosqlite.connect("telegram_leads.db") as db:
                return await operation(db)
        except aiosqlite.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                await asyncio.sleep(0.1 * (2 ** attempt))
            else:
                raise
```

### Graceful Shutdown

```python
import signal

class SystemManager:
    def __init__(self):
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
    
    def setup_signal_handlers(self):
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_event.set()
    
    async def run(self):
        self.setup_signal_handlers()
        
        # Запуск всех сервисов
        self._tasks = [
            asyncio.create_task(self._ingestion_service()),
            asyncio.create_task(self._join_queue_processor()),
            asyncio.create_task(self._message_parser_service()),
            asyncio.create_task(self._llm_verifier_service()),
            asyncio.create_task(self._delivery_bot_service()),
        ]
        
        # Ожидание сигнала остановки
        await self._shutdown_event.wait()
        
        # Graceful shutdown
        logger.info("Stopping new task acceptance...")
        # Установить флаги остановки в каждом сервисе
        
        logger.info("Waiting for active tasks to complete (30s timeout)...")
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout reached, forcing shutdown...")
            for task in self._tasks:
                task.cancel()
        
        # Сохранение состояния
        await self._save_state()
        logger.info("Shutdown complete")
```

## Testing Strategy

### Dual Testing Approach

Система требует комбинации unit-тестов и property-based тестов для обеспечения корректности:

**Unit Tests**: Фокусируются на конкретных примерах, edge cases и интеграционных точках:
- Валидация форматов ссылок (валидные/невалидные примеры)
- Обработка специфических ошибок Telegram API (FloodWait, USER_DEACTIVATED_BAN)
- Корректность формирования промптов с 0, 1, 20 негативными примерами
- Graceful shutdown при различных состояниях системы

**Property-Based Tests**: Верифицируют универсальные свойства на большом количестве сгенерированных входных данных:
- Дедупликация работает для любых текстов
- Нормализация текста идемпотентна
- Распределение чатов соблюдает лимиты для любого количества юзерботов
- Очередь задач сохраняет порядок по времени

### Property-Based Testing Configuration

**Библиотека**: Hypothesis (Python)

**Конфигурация**:
```python
from hypothesis import given, settings
import hypothesis.strategies as st

@settings(max_examples=100)  # Минимум 100 итераций
@given(text=st.text(min_size=1, max_size=1000))
def test_property_X(text):
    # Feature: telegram-lead-monitoring, Property X: <property_text>
    pass
```

**Теги**: Каждый property-based тест должен содержать комментарий:
```python
# Feature: telegram-lead-monitoring, Property 1: Text normalization is idempotent
```

### Test Coverage Requirements

- Unit tests: Минимум 80% покрытие кода
- Property tests: Все свойства из секции Correctness Properties
- Integration tests: End-to-end сценарии (mock Telegram API)
- Load tests: Обработка 1000 сообщений/минуту с 10 юзерботами


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Chat Link Validation

*For any* string input, the system accepts it as a valid chat link if and only if it matches the format `^(https?://)?(t\.me/|@)[\w\d_]+$`

**Validates: Requirements 1.2**

### Property 2: Saved Chats Have Pending Status

*For any* list of valid chat links, after saving to the database, all chats must have status "pending"

**Validates: Requirements 1.4**

### Property 3: All Chats Are Distributed

*For any* non-empty list of chats and non-empty pool of available userbots, after distribution every chat must be assigned to exactly one userbot

**Validates: Requirements 2.1**

### Property 4: Load Balancing

*For any* distribution of chats among userbots, the difference between the maximum and minimum number of chats assigned to any two userbots should not exceed 1 (when possible)

**Validates: Requirements 2.2**

### Property 5: Daily Join Limit Enforcement

*For any* userbot, the number of join tasks assigned to it within a 24-hour period must not exceed 10

**Validates: Requirements 2.3, 2.4**

### Property 6: Join Task Delay Range

*For any* two consecutive join tasks assigned to the same userbot, the difference between their scheduled times must be between 300 and 1800 seconds

**Validates: Requirements 3.1**

### Property 7: Join Tasks Have Scheduled Time

*For any* created join task, it must have a non-null `scheduled_at` timestamp that is in the future relative to creation time

**Validates: Requirements 3.2**

### Property 8: Tasks Execute After Scheduled Time

*For any* join task, its execution must not begin before its `scheduled_at` timestamp

**Validates: Requirements 3.4**

### Property 9: Successful Join Updates Status

*For any* chat where join operation succeeds, the chat status must be updated to "active"

**Validates: Requirements 4.2**

### Property 10: Failed Join Records Error

*For any* chat where join operation fails, the chat status must be updated to "error" and an error message must be recorded

**Validates: Requirements 4.3**

### Property 11: Active Chats Have Subscriptions

*For any* chat with status "active", there must be an active message subscription for that chat

**Validates: Requirements 6.1**

### Property 12: Message Field Extraction

*For any* received Telegram message, the parser must extract all required fields: text, sender_id, sender_username (if available), chat_id, and chat_title

**Validates: Requirements 6.3**

### Property 13: Trigger Word Filtering

*For any* message, it is passed to LLM verification if and only if it contains at least one trigger word (case-insensitive)

**Validates: Requirements 7.2, 7.3**

### Property 14: Case-Insensitive Trigger Matching

*For any* trigger word and any message text, the trigger word should be detected regardless of the case of characters in either the trigger word or the message

**Validates: Requirements 7.4**

### Property 15: LLM Response Is Binary

*For any* LLM verification request, the parsed result must be a boolean value (qualified lead or not)

**Validates: Requirements 8.3**

### Property 16: Qualified Leads Are Delivered

*For any* message classified by LLM as a qualified lead, it must be passed to the delivery bot

**Validates: Requirements 8.4**

### Property 17: LLM Concurrency Limit

*For any* point in time, the number of concurrent LLM API requests must not exceed 10

**Validates: Requirements 8.6**

### Property 18: Spam Examples in Prompt

*For any* LLM verification request, the prompt must include up to 20 most recent examples from the spam database (or fewer if database contains fewer)

**Validates: Requirements 9.1**

### Property 19: Lead Message Format Completeness

*For any* qualified lead delivered to operator, the message must contain all required fields: lead text, sender profile link (format `@username` or `t.me/userid`), chat title, and two inline buttons ("Спам" and "В блок")

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

### Property 20: Spam Feedback Saves to Database

*For any* "Спам" button press by operator, the marked message text must be saved to spam database with a timestamp

**Validates: Requirements 11.1, 11.2**

### Property 21: Spam Feedback Confirmation

*For any* "Спам" button press, the operator must receive a confirmation message

**Validates: Requirements 11.3**

### Property 22: Block Feedback Updates Both Tables

*For any* "В блок" button press, both the sender must be added to blocklist AND the message must be added to spam database

**Validates: Requirements 11.4**

### Property 23: Valid Session Adds Active Userbot

*For any* valid Telegram session file, adding it to the system must result in a new userbot with status "active" in the pool

**Validates: Requirements 12.3**

### Property 24: Unresponsive Userbot Marked Unavailable

*For any* userbot that fails health check, its status must be updated to "unavailable"

**Validates: Requirements 13.2**

### Property 25: Status Change Triggers Notification

*For any* userbot status change to "banned" or "unavailable", an administrator notification must be sent

**Validates: Requirements 13.4**

### Property 26: Comprehensive Event Logging

*For any* significant system event (join attempt, LLM API call, lead delivery, or error), a log entry must be created with complete information (component, event type, timestamp, relevant data)

**Validates: Requirements 14.1, 14.2, 14.3, 14.4**

### Property 27: Userbots Are Read-Only

*For any* userbot operation, it must be a read operation (join chat, read messages) and never a write operation (send message, edit message, delete message)

**Validates: Requirements 15.1, 15.2, 15.3**

### Property 28: Send Attempts Are Blocked and Logged

*For any* attempt to send a message through a userbot, the operation must be blocked and a warning must be logged

**Validates: Requirements 15.4**

### Property 29: FloodWait Suspends Userbot

*For any* FloodWait error received from Telegram API, the affected userbot must be suspended for the duration specified in the error

**Validates: Requirements 16.1**

### Property 30: Telegram API Rate Limiting

*For any* one-second time window, a single userbot must not make more than 20 requests to Telegram API

**Validates: Requirements 16.2**

### Property 31: FloodWait Triggers Task Redistribution

*For any* userbot suspended due to FloodWait, its pending tasks must be redistributed to other available userbots

**Validates: Requirements 16.3**

### Property 32: Automatic Userbot Resumption

*For any* userbot suspended due to FloodWait, its status must automatically return to "active" after the suspension duration expires

**Validates: Requirements 16.4**

### Property 33: Invalid Configuration Raises Error

*For any* configuration file with missing required fields or invalid values, loading it must raise a validation error

**Validates: Requirements 17.3**

### Property 34: State Persistence

*For any* change to system state (chat status, join task status), the change must be persisted to the database

**Validates: Requirements 18.1, 18.2**

### Property 35: State Recovery After Restart

*For any* system restart, the restored state must match the state that was persisted before shutdown

**Validates: Requirements 18.3**

### Property 36: Text Normalization for Hashing

*For any* message text, its hash must be computed only from the normalized version (with URLs, emojis, special characters, and whitespace removed)

**Validates: Requirements 19.1**

### Property 37: Text Normalization Is Idempotent

*For any* message text, applying normalization twice must produce the same result as applying it once: `normalize(normalize(text)) == normalize(text)`

**Validates: Requirements 19.1**

### Property 38: Message Hash Persistence

*For any* processed message, its hash must be saved to the database with a timestamp

**Validates: Requirements 19.2**

### Property 39: Duplicate Detection Within 24 Hours

*For any* two messages with identical normalized text, if they arrive within 24 hours of each other, the second message must be discarded without processing

**Validates: Requirements 19.3**

### Property 40: Hash Cleanup After 24 Hours

*For any* message hash in the database, if its timestamp is older than 24 hours, it must be removed from the database

**Validates: Requirements 19.4**

### Property 41: Shutdown Stops New Task Acceptance

*For any* system shutdown signal (SIGTERM or SIGINT), after the signal is received, no new tasks must be accepted by any component

**Validates: Requirements 20.1**

### Property 42: Shutdown Persists Incomplete Tasks

*For any* incomplete task at shutdown time, its current state must be saved to the database before the system terminates

**Validates: Requirements 20.3**

