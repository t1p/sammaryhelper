# Инструкции по установке и запуску Sammaryhelper

## Требования
- Python 3.8+
- PostgreSQL (для кеширования данных)
- Доступ к Telegram API (api_id и api_hash)
- Доступ к OpenAI API (API ключ)

## Установка и запуск

### Windows
1. **Клонирование репозитория**
   ```bash
   git clone https://github.com/yourusername/sammaryhelper.git
   cd sammaryhelper
   ```

2. **Создание виртуального окружения**
   ```bash
   python -m venv venv
   ```

3. **Активация виртуального окружения**
   - Для PowerShell (с правами на выполнение скриптов):
     ```bash
     .\venv\Scripts\Activate.ps1
     ```
   - Или для cmd:
     ```bash
     venv\Scripts\activate.bat
     ```

4. **Установка зависимостей**
   ```bash
   pip install -r requirements.txt
   ```

5. **Настройка PostgreSQL**
   - Установите PostgreSQL, если он еще не установлен
   - Создайте базу данных `telegram_summarizer`
   - Настройте доступ к базе данных в конфигурационном файле

6. **Запуск приложения**
   ```bash
   python -m Sammaryhelper.main
   ```

### Linux/MacOS
1. **Клонирование репозитория**
   ```bash
   git clone https://github.com/yourusername/sammaryhelper.git
   cd sammaryhelper
   ```

2. **Создание виртуального окружения**
   ```bash
   python -m venv venv
   ```

3. **Активация виртуального окружения**
   ```bash
   source venv/bin/activate
   ```

4. **Установка зависимостей**
   ```bash
   pip install -r requirements.txt
   ```

5. **Настройка PostgreSQL**
   - Установите PostgreSQL, если он еще не установлен
   - Создайте базу данных `telegram_summarizer`
   - Настройте доступ к базе данных в конфигурационном файле

6. **Запуск приложения**
   ```bash
   python -m Sammaryhelper.main
   ```

## Настройка конфигурации
1. При первом запуске приложение создаст шаблон конфигурационного файла в директории `configs`
2. Отредактируйте файл, добавив:
   - Ваш Telegram API ID и API Hash (получите на https://my.telegram.org)
   - Ваш OpenAI API ключ
   - Настройки подключения к PostgreSQL

## Устранение проблем
- Если возникают проблемы с активацией виртуального окружения в PowerShell, попробуйте запустить PowerShell с правами администратора и выполнить:
  ```
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- При проблемах с установкой `asyncpg==0.29.0e`, используйте:
  ```
  pip install asyncpg
  ```
- Если возникают ошибки подключения к PostgreSQL, проверьте:
  - Запущен ли сервер PostgreSQL
  - Правильность учетных данных в конфигурационном файле
  - Существование базы данных `telegram_summarizer`