# Инструкция по запуску на Windows Server 2022

## Текущая ситуация
Python 3.12 установлен по пути: `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`

Все batch-файлы уже настроены и автоматически найдут Python по этому пути.

## Быстрый старт

### 1. Запустить Dashboard для настройки
```cmd
cd C:\путь\к\production
dashboard.bat
```

Dashboard откроется в браузере. Заполните в нём:
- Bot Token (от @BotFather)
- Operator Chat ID (ваш Telegram ID)
- Telegram API ID (от https://my.telegram.org)
- Telegram API Hash (от https://my.telegram.org)
- LLM API Key (Claude или OpenAI)

### 2. Запустить систему
```cmd
start.bat
```

## Опциональная настройка PATH (рекомендуется)

Чтобы команда `python` работала везде, добавьте Python в PATH:

1. Откройте cmd **от имени администратора**
2. Выполните:
```cmd
setx /M PATH "%PATH%;C:\Users\Administrator\AppData\Local\Programs\Python\Python312;C:\Users\Administrator\AppData\Local\Programs\Python\Python312\Scripts"
```
3. Закройте и откройте cmd заново
4. Проверьте: `python --version`

## Доступные утилиты

- `dashboard.bat` - веб-интерфейс для настройки и мониторинга
- `start.bat` - запуск основной системы
- `check_status.bat` - проверка статуса системы
- `clear_pending_tasks.bat` - очистка зависших задач
- `get_code.bat` - получение кода подтверждения для Telegram

## Структура папок

- `sessions/` - файлы сессий Telegram (создаются автоматически)
- `config.json` - конфигурация (заполняется через dashboard)
- `venv/` - виртуальное окружение Python (создаётся автоматически)

## Важно

- База данных пустая, без тестовых данных
- Все API ключи нужно заполнить через dashboard
- Session файлы будут создаваться в папке `sessions/`
- При первом запуске система создаст виртуальное окружение и установит зависимости

## Решение проблем

### Python не найден
Batch-файлы автоматически ищут Python в:
1. Команда `python`
2. Команда `py` (Microsoft Store)
3. Команда `python3`
4. Hardcoded путь: `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`

Если всё равно не работает, проверьте что Python установлен: `find_python.bat`

### Dashboard не запускается
1. Убедитесь что Python найден
2. Проверьте что файл `config.json` существует
3. Запустите `start.bat` сначала - он создаст venv и установит зависимости

### Система не стартует
1. Проверьте что все API ключи заполнены в `config.json`
2. Проверьте логи в консоли
3. Используйте `check_status.bat` для диагностики
