# План реализации исправления бага с задержками задач

- [x] 1. НАЙТИ КОРНЕВУЮ ПРИЧИНУ - Полный аудит всех мест создания задач
  - Найти ВСЕ места в коде где выполняется INSERT INTO join_tasks
  - Проверить main.py::_process_pending_chats() - вызывает ли enqueue_join_tasks() и добавляет ли в join_queue
  - Проверить dashboard.py - есть ли там создание задач напрямую
  - Проверить src/ingestion/ingestion_module.py::enqueue_join_tasks() - правильно ли вычисляются задержки
  - Проверить все импорты IngestionModule - создается ли несколько экземпляров с разными конфигами
  - Проверить config.py - перезагружается ли конфиг где-то в коде
  - Задокументировать ВСЕ найденные пути создания задач и их параметры
  - _Requirements: 2.2, 2.3, 2.4_

- [x] 2. ИСПРАВИТЬ ОСНОВНУЮ ПРОБЛЕМУ - Добавление задач в очередь после создания
  - **КРИТИЧНО**: Это главное исправление, без которого ничего не работает
  - В main.py::_process_pending_chats() после вызова enqueue_join_tasks(distribution):
    - Извлечь созданные задачи из базы данных (SELECT task_id, userbot_id, chat_id, scheduled_at FROM join_tasks WHERE status='pending' ORDER BY id DESC LIMIT N)
    - Для каждой задачи вызвать await self.join_queue.add_task(task_id, userbot_id, chat_id, scheduled_at)
    - Добавить логирование: print(f"✓ Добавлено {count} задач в очередь выполнения")
  - Убедиться что используется timezone.utc для всех datetime операций
  - Проверить что scheduled_at правильно парсится из базы данных
  - _Requirements: 2.1, 2.2, 2.4_

- [x] 3. ИСПРАВИТЬ ОТОБРАЖЕНИЕ - check_status.py показывает правильные задержки
  - Изменить SQL запрос: добавить created_at в SELECT
  - Вычислять изначальную задержку: delay_seconds = (scheduled_at - created_at).total_seconds()
  - Вычислять оставшееся время: remaining_seconds = (scheduled_at - now).total_seconds()
  - Показывать: "Задержка при создании: {delay_seconds} сек ({delay_seconds/60:.1f} мин)"
  - Показывать: "Выполнится через: {remaining_seconds/60:.1f} мин" (или "ПРОСРОЧЕНО на {abs(remaining_seconds)/60:.1f} мин" если scheduled_at < now)
  - Использовать timezone-aware datetime для всех операций
  - _Requirements: 2.1, 2.5_

- [x] 4. ОЧИСТКА СТАРЫХ ЗАДАЧ - Предотвратить накопление просроченных задач
  - В src/ingestion/join_queue.py::load_pending_tasks() добавить фильтр времени
  - Изменить SQL: WHERE status = 'pending' AND created_at > datetime('now', '-1 hour')
  - Добавить метод cleanup_old_tasks() который помечает просроченные задачи как 'failed'
  - Вызывать cleanup_old_tasks() при старте системы
  - _Requirements: 2.1_

- [x] 5. ПРОВЕРКА ИСПРАВЛЕНИЯ - Убедиться что баг исправлен
  - Запустить nuclear_clean.py для полной очистки базы
  - Добавить тестовый чат через дашборд
  - Проверить что задача создается с задержкой 60-104 секунды (не 420+ минут)
  - Проверить что задача добавляется в join_queue (размер очереди > 0)
  - Запустить check_status.bat и проверить что показывается правильная задержка
  - Подождать время задержки и проверить что задача выполнилась
  - Перезапустить систему и проверить что старые задачи не загружаются
  - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [x] 6. НАПИСАТЬ АВТОТЕСТ - Проверка что исправление работает
  - Написать тест test_task_delay_fix.py который:
    - Создает pending чат
    - Вызывает _process_pending_chats()
    - Проверяет что задача создана в БД с delay 60-104 секунды
    - Проверяет что задача добавлена в join_queue
    - Проверяет что scheduled_at = created_at + delay
  - Запустить тест и убедиться что проходит
  - _Requirements: 2.1, 2.2, 2.4_

- [ ] 7. ОЧИСТКА ТЕСТОВЫХ ДАННЫХ - Удалить весь мусор после тестирования
  - Удалить все тестовые файлы автотестов (test_task2_verification.py, test_real_database.py, test_real_delays.py, test_full_flow.py и т.д.)
  - Удалить тестовые аккаунты из таблицы userbots (несуществующие аккаунты созданные для тестов)
  - Удалить тестовые каналы из таблицы chats (левые каналы добавленные для тестов)
  - Удалить тестовые задачи из таблицы join_tasks
  - Удалить документацию тестирования (ROOT_CAUSE_AUDIT.md, TASK2_VERIFICATION_SUMMARY.md и т.д.)
  - Оставить только продакшн код и реальные данные
  - _Requirements: Очистка после разработки_
