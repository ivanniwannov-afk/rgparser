# Telegram Lead Monitoring System - Production Build

Это production-версия системы мониторинга лидов в Telegram с исправленными критическими багами.

## Структура проекта

```
production/
├── main.py                          # Точка входа приложения
├── database.py                      # Управление базой данных SQLite
├── config.py                        # Конфигурация системы
├── requirements.txt                 # Python зависимости
├── .env.example                     # Пример файла конфигурации
├── start.bat                        # Скрипт запуска (Windows)
├── install_service.bat              # Установка как службы (Windows)
└── src/
    ├── bot/
    │   └── operator_bot.py          # Telegram бот оператора
    ├── delivery/
    │   └── delivery_bot.py          # Доставка лидов оператору
    ├── ingestion/
    │   ├── join_logic.py            # Логика вступления в чаты
    │   ├── join_queue.py            # Очередь задач вступления
    │   └── ingestion_module.py      # Модуль сбора данных
    ├── logging/
    │   └── activity_logger.py       # Логирование активности
    ├── parser/
    │   └── message_parser.py        # Парсинг сообщений
    ├── userbot/
    │   └── userbot_pool_manager.py  # Управление пулом юзерботов
    └── verifier/
        └── llm_verifier.py          # LLM верификация лидов
```

## Установка

1. Установите Python 3.10+
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. Скопируйте `.env.example` в `.env` и заполните:
   ```bash
   cp .env.example .env
   ```

4. Настройте `.env` файл:
   - `BOT_TOKEN` - токен Telegram бота
   - `OPERATOR_CHAT_ID` - ID чата оператора
   - `OPENAI_API_KEY` - ключ OpenAI API
   - `TRIGGER_WORDS` - ключевые слова для поиска
   - `DAILY_JOIN_LIMIT` - лимит вступлений в день (по умолчанию 10)

## Запуск

### Linux/macOS:
```bash
python main.py
```

### Windows:
```bash
start.bat
```

### Как служба Windows:
```bash
install_service.bat
```

## Исправленные критические баги

### Категория 1: Event Loop Blocking
- ✅ Event-driven wakeup для FloodWait (не блокирует другие задачи)
- ✅ Antibot sleep сокращен с 60 до 2 секунд

### Категория 2: Database State Management
- ✅ Dead bots помечаются как 'banned' при ошибке клиента
- ✅ assigned_userbot_id сбрасывается при ошибке вступления
- ✅ Статус чата обновляется при ошибке получения клиента

### Категория 3: SQLite Concurrency
- ✅ Shared write lock предотвращает "database is locked"
- ✅ UPSERT обрабатывает дубликаты при перезапуске
- ✅ lastrowid предотвращает race conditions
- ✅ HTTP API вместо Pyrogram для уведомлений (нет блокировок сессий)

### Категория 4: Telegram API Limits
- ✅ RetryAfter обработка с retry logic (до 3 попыток)
- ✅ Polling запущен для inline button callbacks
- ✅ FloodWait уведомления в консоль и Telegram

## Требования к системе

- Python 3.10+
- SQLite 3.35+ (с поддержкой WAL mode)
- 512 MB RAM минимум
- Интернет соединение

## Безопасность

- Храните `.env` файл в безопасности
- Не коммитьте `.env` в git
- Регулярно обновляйте зависимости
- Используйте отдельные API ключи для разных окружений

## Поддержка

При возникновении проблем проверьте:
1. Логи в `activity_logs` таблице базы данных
2. Консольный вывод для FloodWait предупреждений
3. Telegram уведомления оператору

## База данных

База данных SQLite создается автоматически при первом запуске:
- `telegram_leads.db` - основная база данных
- Включен WAL mode для лучшей конкурентности
- Автоматическая миграция схемы

## Лицензия

Proprietary - все права защищены
