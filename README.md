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
├── get_code.bat                     # Создание session файлов
├── get_code.py                      # Утилита создания sessions
├── dashboard.bat                    # Запуск веб-дашборда
├── dashboard.py                     # Веб-интерфейс управления
├── check_status.bat                 # Проверка статуса системы
├── check_status.py                  # Утилита проверки статуса
├── clear_pending_tasks.bat          # Очистка pending задач
├── clear_pending_tasks.py           # Утилита очистки задач
├── sessions/                        # Папка для .session файлов юзерботов
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

5. Создайте session файлы для юзерботов:
   ```bash
   get_code.bat
   ```
   
   Это создаст `.session` файлы в папке `sessions/`. Вам понадобится:
   - Telegram API ID и API Hash (получите на https://my.telegram.org/apps)
   - Номер телефона для каждого юзербота
   - Код подтверждения из Telegram
   
   Система автоматически загрузит все `.session` файлы из папки `sessions/` при запуске.

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

## Утилиты управления

### Создание Session Файлов
```bash
get_code.bat
```
Интерактивная утилита для создания Telegram session файлов. Вам понадобится:
- API ID и API Hash с https://my.telegram.org/apps
- Номер телефона для юзербота
- Код подтверждения из Telegram

Session файлы сохраняются в папку `sessions/` и автоматически загружаются при запуске системы.

### Dashboard (Веб-интерфейс)
```bash
dashboard.bat
```
Открывает веб-дашборд для:
- Мониторинга системы в реальном времени
- Управления каналами (добавление/удаление)
- Настройки триггерных слов
- Управления API ключами
- Просмотра логов активности
- Мониторинга статуса юзерботов

Дашборд автоматически откроется в браузере по адресу http://localhost:8501

### Проверка статуса системы
```bash
check_status.bat
```
Показывает текущий статус системы:
- Статистика юзерботов (активные/всего)
- Статистика чатов (pending/active/error)
- Статус очереди задач вступления
- Последние логи активности
- Запланированные задачи с задержками

### Очистка pending задач
```bash
clear_pending_tasks.bat
```
Очищает все pending задачи вступления и сбрасывает pending чаты. Используйте когда:
- Задачи застряли в pending состоянии
- Нужно сбросить очередь
- Система требует свежего старта

**Внимание:** Это удалит все pending задачи. Система пересоздаст их с новыми задержками.

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
