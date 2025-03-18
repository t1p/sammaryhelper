from telethon import TelegramClient
from telethon.tl.types import Channel, User
from telethon.tl import functions
import os
from typing import List, Dict, Any
from .db_handler import DatabaseHandler
import datetime

class TelegramClientBase:
    """Базовый класс для работы с Telegram API"""
    
    def __init__(self, config):
        self.config = config
        self.client = None
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Параметры версии клиента
        self.system_version = config.get('system_version', 'Windows 10')
        self.device_model = config.get('device_model', 'Desktop')
        self.app_version = config.get('app_version', '4.8.1')
        
        # Инициализация обработчика базы данных
        self.db_handler = None
        self.use_cache = config.get('use_cache', True)
        
    def log(self, message):
        """Логирование сообщений"""
        if self.config.get('debug', False):
            print(message)  # Выводим в консоль только если включен режим отладки

    async def init_client(self):
        """Инициализация клиента Telegram"""
        try:
            if hasattr(self, 'client') and self.client is not None:
                if self.client.is_connected():
                    await self.client.disconnect()
                self.client = None

            # Загружаем конфиг
            config_path = os.path.join(self.app_dir, "configs", f"{self.config['config_name']}.py")
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"Файл конфига не найден: {config_path}")

            # Импортируем конфиг
            import importlib.util
            spec = importlib.util.spec_from_file_location("config", config_path)
            config = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config)

            # Создаем директорию для сессий
            sessions_dir = os.path.join(self.app_dir, "sessions")
            os.makedirs(sessions_dir, exist_ok=True)
            session_name = os.path.join(sessions_dir, self.config['config_name'])

            # Настройки прокси
            proxy_settings = None
            if hasattr(config, 'use_proxy') and config.use_proxy and hasattr(config, 'proxy_settings'):
                proxy_settings = (
                    config.proxy_settings['proxy_type'],
                    config.proxy_settings['proxy_host'],
                    config.proxy_settings['proxy_port']
                )

            # Создаем клиент с указанными параметрами версии
            self.client = TelegramClient(
                session_name,
                config.api_id,
                config.api_hash,
                proxy=proxy_settings,
                system_version=self.system_version,
                device_model=self.device_model,
                app_version=self.app_version
            )

            # Подключаемся
            await self.client.connect()
            if not await self.client.is_user_authorized():
                await self.client.start()
                
            # Инициализируем обработчик базы данных, если используется кеширование
            if self.use_cache:
                self.log("Начинаю инициализацию клиента...")
                try:
                    self.db_handler = DatabaseHandler(debug=self.config.get('debug', False))
                    db_connected = await self.db_handler.init_connection()
                    if not db_connected:
                        self.log("Не удалось подключиться к базе данных. Кеширование отключено.")
                        self.use_cache = False
                except Exception as e:
                    self.log(f"Ошибка при инициализации базы данных: {e}")
                    self.use_cache = False

            return True

        except Exception as e:
            raise Exception(f"Ошибка при инициализации клиента: {str(e)}")

    async def get_client_info(self):
        """Получение информации о текущих параметрах клиента"""
        if self.client and self.client.is_connected():
            return {
                "system_version": self.client.system_version,
                "device_model": self.client.device_model,
                "app_version": self.client.app_version,
                "layer": self.client.session.layer,  # Версия MTProto
                "dc_id": self.client.session.dc_id,  # ID дата-центра
            }
        return None

    async def close(self):
        """Закрытие подключений"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        
        if self.db_handler:
            await self.db_handler.close()