import asyncio
import sys
import os

# Добавляем путь к директории Sammaryhelper
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Sammaryhelper')))
from Sammaryhelper.telegram_client_base import TelegramClientBase

async def test_init_client():
    config = {
        'config_name': 'config_0707',  # Используем существующий файл конфигурации
        'system_version': 'Windows 10',
        'device_model': 'Desktop',
        'app_version': '4.8.1',
        'use_cache': True,
        'debug': True,
        'api_id': 'your_api_id',  # Замените на ваш API ID
        'api_hash': 'your_api_hash'  # Замените на ваш API Hash
    }
    
    client_base = TelegramClientBase(config)
    try:
        await client_base.init_client()
        print("Клиент успешно инициализирован.")
    except Exception as e:
        print(f"Ошибка при инициализации клиента: {e}")

if __name__ == "__main__":
    asyncio.run(test_init_client())