from telethon import TelegramClient
from telethon.tl.types import Channel, User
from telethon.tl import functions
import os
from typing import List, Dict, Any

class TelegramClientManager:
    def __init__(self, config):
        self.config = config
        self.client = None
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Параметры версии клиента
        self.system_version = config.get('system_version', 'Windows 10')
        self.device_model = config.get('device_model', 'Desktop')
        self.app_version = config.get('app_version', '4.8.1')

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

            return True

        except Exception as e:
            raise Exception(f"Ошибка при инициализации клиента: {str(e)}")

    async def get_dialogs(self):
        """Получение списка диалогов"""
        dialogs = []
        async for dialog in self.client.iter_dialogs():
            dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
            dialogs.append({
                'id': dialog.id,
                'name': dialog.name,
                'type': dialog_type,
                'entity': dialog.entity
            })
        return dialogs

    async def get_chat_participants(self, chat_id: int) -> List[Dict[str, Any]]:
        """Получение списка участников чата"""
        try:
            participants = []
            async for user in self.client.iter_participants(chat_id):
                participants.append({
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                })
            return participants
        except Exception as e:
            raise Exception(f"Ошибка при получении участников чата: {e}")

    async def filter_messages(self, chat_id: int, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Фильтрация сообщений по заданным критериям"""
        try:
            messages = []
            async for message in self.client.iter_messages(chat_id, search=filters.get('search'), limit=filters.get('limit')):
                sender_name = "Неизвестно"
                if message.sender_id:
                    try:
                        sender = await self.client.get_entity(message.sender_id)
                        if isinstance(sender, User):
                            sender_name = getattr(sender, 'username', sender.first_name or 'Неизвестно')
                        elif isinstance(sender, Channel):
                            sender_name = sender.title  # Используем название канала для Channel
                    except Exception as e:
                        self.log(f"Ошибка при получении отправителя: {e}")
                
                # Применяем фильтр по типу медиа
                if filters.get('filter') == 'photo' and not message.photo:
                    continue
                if filters.get('filter') == 'video' and not message.video:
                    continue
                
                messages.append({
                    'id': message.id,
                    'text': message.text or '',
                    'date': message.date,
                    'sender_id': message.sender_id,
                    'sender_name': sender_name,
                    'media': message.media
                })
            return messages
        except Exception as e:
            raise Exception(f"Ошибка при фильтрации сообщений: {e}")

    async def filter_dialogs(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Фильтрация диалогов по заданным критериям"""
        try:
            dialogs = []
            async for dialog in self.client.iter_dialogs(limit=filters.get('limit')):
                dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
                
                # Применяем фильтр по имени
                if filters.get('search') and filters['search'].lower() not in dialog.name.lower():
                    continue
                
                dialogs.append({
                    'id': dialog.id,
                    'name': dialog.name,
                    'type': dialog_type,
                    'entity': dialog.entity,
                    'folder_id': dialog.folder_id  # Используем folder_id
                })
            
            # Логируем список диалогов перед сортировкой
            print(f"Диалоги перед сортировкой: {dialogs}")
            
            # Сортировка
            sort_key = filters.get('sort', 'name')
            if sort_key == 'folder':
                dialogs.sort(key=lambda x: x['folder_id'] if x['folder_id'] is not None else -1)
            else:
                dialogs.sort(key=lambda x: x[sort_key])
            
            # Логируем список диалогов после сортировки
            print(f"Диалоги после сортировки: {dialogs}")
            
            return dialogs
        except Exception as e:
            print(f"Ошибка при фильтрации диалогов: {e}")
            raise Exception(f"Ошибка при фильтрации диалогов: {e}")

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

    async def get_dialog_folders(self) -> Dict[int, str]:
        """Получение папок и их содержимого"""
        try:
            folders = {}
            result = await self.client(functions.messages.GetDialogFilters())
            for folder in result:
                for peer in folder.pinned_peers:
                    folders[peer.channel_id] = folder.title
            return folders
        except Exception as e:
            raise Exception(f"Ошибка при получении папок: {e}") 