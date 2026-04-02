# Bugfix Requirements Document: Production Critical Fixes

## Introduction

Данный документ описывает критические проблемы в системе мониторинга лидов Telegram, выявленные при аудите архитектуры перед запуском в продакшен. Проблемы охватывают четыре категории: блокировка Event Loop, менеджмент состояний БД, race conditions в SQLite, и лимиты Telegram API. Без исправления эти баги приведут к блокировкам системы, крашам базы данных и потере лидов при высокой нагрузке.

## Bug Analysis

### Current Behavior (Defect)

#### 1. Event Loop Blocking Issues

1.1 WHEN воркер очереди берет задачу с FloodWait (например, 400 минут) THEN система использует `asyncio.wait_for` с жестким таймаутом, блокируя воркер и парализуя обработку других задач с короткими таймерами

1.2 WHEN юзербот проходит антибот-защиту после вступления в чат THEN система выполняет `asyncio.sleep(60)`, замораживая поток на 60 секунд

#### 2. Database State Management Issues

1.3 WHEN клиент юзербота не стартует (бан/битая сессия) THEN `userbot_pool_manager` возвращает `None`, но статус остается `ACTIVE`, и пул продолжает назначать задачи этому боту

1.4 WHEN задача вступления в чат падает с ошибкой THEN поле `assigned_userbot_id` чата не сбрасывается в `NULL`, и чат зависает в статусе `pending` с привязанным ботом

1.5 WHEN не удается получить клиента в `join_logic.execute_join()` THEN функция возвращает `False`, но статус чата не обновляется на `error`, и задача исчезает без следа

#### 3. SQLite Concurrency Issues

1.6 WHEN несколько юзерботов одновременно парсят сообщения и пытаются записать лидов в БД THEN возникает ошибка "database is locked" из-за конкурентных `INSERT` операций

1.7 WHEN система перезапускается и пытается вставить юзерботов в БД THEN возникает `IntegrityError` из-за дубликатов `session_file` при слепом `INSERT`

1.8 WHEN `ingestion_module` создает задачи и ищет ID чатов через `SELECT ... ORDER BY DESC LIMIT 1` THEN при конкурентном парсинге ID перепутываются из-за race condition

1.9 WHEN система отправляет уведомления о капче THEN инициализируется полный клиент Pyrogram, вызывая блокировку файлов сессий

#### 4. Telegram API Limits Issues

1.10 WHEN `delivery_bot` отправляет сообщения и получает `telegram.error.RetryAfter` THEN лиды теряются в блоке `except`, так как нет обработки этой ошибки

1.11 WHEN `delivery_bot` отправляет сообщения с инлайн-кнопками THEN кнопки не работают, потому что бот не запускает `start_polling()` для прослушивания коллбеков

1.12 WHEN юзербот получает FloodWait от Telegram THEN ошибка логируется в тихий лог, и система не уведомляет оператора о бане

### Expected Behavior (Correct)

#### 1. Event Loop Blocking Fixes

2.1 WHEN воркер очереди берет задачу с FloodWait THEN система SHALL использовать событийно-управляемую модель через `asyncio.Event` для мгновенного пробуждения воркера при появлении новых задач с короткими таймерами

2.2 WHEN юзербот проходит антибот-защиту после вступления в чат THEN система SHALL минимизировать задержку до 2-3 секунд вместо 60 секунд

#### 2. Database State Management Fixes

2.3 WHEN клиент юзербота не стартует (бан/битая сессия) THEN система SHALL помечать юзербота статусом `error` или `banned` в БД

2.4 WHEN задача вступления в чат падает с ошибкой THEN система SHALL сбрасывать `assigned_userbot_id` чата в `NULL` и обновлять статус чата на `error`

2.5 WHEN не удается получить клиента в `join_logic.execute_join()` THEN система SHALL обновлять статус чата на `error` с соответствующим сообщением об ошибке

#### 3. SQLite Concurrency Fixes

2.6 WHEN несколько юзерботов одновременно парсят сообщения и пытаются записать лидов в БД THEN система SHALL использовать `asyncio.Lock()` на операции записи для предотвращения "database is locked"

2.7 WHEN система перезапускается и пытается вставить юзерботов в БД THEN система SHALL использовать UPSERT (`INSERT OR REPLACE`) или проверку существования перед вставкой

2.8 WHEN `ingestion_module` создает задачи THEN метод SHALL возвращать `lastrowid` вместо поиска через `SELECT ... ORDER BY DESC LIMIT 1`

2.9 WHEN система отправляет уведомления о капче THEN система SHALL использовать простой HTTP-запрос через `aiohttp` вместо инициализации полного клиента Pyrogram

#### 4. Telegram API Limits Fixes

2.10 WHEN `delivery_bot` отправляет сообщения и получает `telegram.error.RetryAfter` THEN система SHALL ожидать указанное время и повторять отправку

2.11 WHEN `delivery_bot` отправляет сообщения с инлайн-кнопками THEN бот SHALL запускать `start_polling()` для прослушивания коллбеков

2.12 WHEN юзербот получает FloodWait от Telegram THEN система SHALL явно выводить предупреждение в консоль, ставить бота на паузу и перекидывать задачи на других ботов

### Unchanged Behavior (Regression Prevention)

#### 1. Event Loop Behavior

3.1 WHEN воркер очереди обрабатывает задачи без FloodWait THEN система SHALL CONTINUE TO обрабатывать задачи в порядке приоритета по `scheduled_at`

3.2 WHEN юзербот вступает в чат без антибот-защиты THEN система SHALL CONTINUE TO вступать в чат без дополнительных задержек

#### 2. Database State Management

3.3 WHEN клиент юзербота успешно стартует THEN система SHALL CONTINUE TO помечать юзербота статусом `active` и назначать ему задачи

3.4 WHEN задача вступления в чат выполняется успешно THEN система SHALL CONTINUE TO обновлять статус чата на `active` и сохранять `chat_id`, `chat_title`, `joined_at`

3.5 WHEN клиент успешно получен в `join_logic.execute_join()` THEN система SHALL CONTINUE TO выполнять вступление в чат

#### 3. SQLite Operations

3.6 WHEN один юзербот парсит сообщения и записывает лидов в БД THEN система SHALL CONTINUE TO записывать лидов без ошибок

3.7 WHEN система стартует впервые и вставляет юзерботов в БД THEN система SHALL CONTINUE TO создавать записи без ошибок

3.8 WHEN `ingestion_module` создает задачи последовательно THEN система SHALL CONTINUE TO корректно связывать задачи с чатами

3.9 WHEN система отправляет обычные уведомления (не о капче) THEN система SHALL CONTINUE TO отправлять уведомления через существующие механизмы

#### 4. Telegram API Operations

3.10 WHEN `delivery_bot` отправляет сообщения без превышения лимитов THEN система SHALL CONTINUE TO доставлять лиды оператору

3.11 WHEN `delivery_bot` отправляет сообщения без инлайн-кнопок THEN система SHALL CONTINUE TO доставлять сообщения корректно

3.12 WHEN юзербот выполняет операции без FloodWait THEN система SHALL CONTINUE TO выполнять операции без дополнительных задержек
