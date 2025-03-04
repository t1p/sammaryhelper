from telethon import TelegramClient
from telethon.tl.types import Channel, User
from telethon.tl import functions
import os
from typing import List, Dict, Any
from .db_handler import DatabaseHandler

class TelegramClientManager:
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
            # Проверяем, можно ли использовать кеш
            if self.use_cache and self.db_handler and not filters.get('force_refresh'):
                # Получаем аккаунт ID
                me = await self.client.get_me()
                account_id = str(me.phone) if me.phone else me.username
                
                # Проверяем кеш
                cached_messages = await self.db_handler.get_cached_messages(chat_id, account_id)
                if cached_messages:
                    self.log(f"Используем кешированные сообщения ({len(cached_messages)})")
                    
                    # Применяем фильтры к кешированным данным
                    filtered_messages = []
                    for message in cached_messages:
                        # Применяем фильтр по тексту
                        if filters.get('search') and filters['search'].lower() not in message.get('text', '').lower():
                            continue
                        
                        # Применяем фильтр по типу медиа
                        if filters.get('filter') == 'photo' and not message.get('photo'):
                            continue
                        if filters.get('filter') == 'video' and not message.get('video'):
                            continue
                        
                        filtered_messages.append(message)
                    
                    # Ограничиваем количество сообщений
                    if filters.get('limit'):
                        filtered_messages = filtered_messages[:filters.get('limit')]
                    
                    return filtered_messages
            
            # Если кеш не используется или данных в кеше нет, получаем данные из Telegram
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
                    'media': message.media,
                    'photo': bool(message.photo),
                    'video': bool(message.video)
                })
            
            # Кешируем результаты, если используется кеширование
            if self.use_cache and self.db_handler:
                me = await self.client.get_me()
                account_id = str(me.phone) if me.phone else me.username
                
                # Создаем копию списка без объекта media, который нельзя сериализовать
                messages_to_cache = []
                for message in messages:
                    message_copy = message.copy()
                    if 'media' in message_copy:
                        del message_copy['media']
                    messages_to_cache.append(message_copy)
                
                await self.db_handler.cache_messages(messages_to_cache, chat_id, account_id)
            
            return messages
        except Exception as e:
            raise Exception(f"Ошибка при фильтрации сообщений: {e}")

    async def filter_dialogs(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Фильтрация диалогов по заданным критериям"""
        try:
            # Проверяем, можно ли использовать кеш
            if self.use_cache and self.db_handler:
                # Получаем аккаунт ID (используем номер телефона или имя пользователя)
                me = await self.client.get_me()
                account_id = str(me.phone) if me.phone else me.username
                
                # Проверяем кеш
                cached_dialogs = await self.db_handler.get_cached_dialogs(account_id)
                if cached_dialogs and not filters.get('force_refresh'):
                    self.log(f"Используем кешированные диалоги ({len(cached_dialogs)})")
                    
                    # Применяем фильтры к кешированным данным
                    filtered_dialogs = []
                    for dialog in cached_dialogs:
                        # Применяем фильтр по имени
                        if filters.get('search') and filters['search'].lower() not in dialog['name'].lower():
                            continue
                        filtered_dialogs.append(dialog)
                    
                    # Сортировка
                    sort_key = filters.get('sort', 'name')
                    if sort_key == 'folder':
                        filtered_dialogs.sort(key=lambda x: x['folder_id'] if x['folder_id'] is not None else -1)
                    else:
                        filtered_dialogs.sort(key=lambda x: x[sort_key])
                    
                    return filtered_dialogs
            
            # Если кеш не используется или данных в кеше нет, получаем данные из Telegram
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
                    'folder_id': dialog.folder_id,  # Используем folder_id
                    'unread_count': dialog.unread_count  # Добавляем количество непрочитанных сообщений
                })
            
            # Сортировка
            sort_key = filters.get('sort', 'name')
            if sort_key == 'folder':
                dialogs.sort(key=lambda x: x['folder_id'] if x['folder_id'] is not None else -1)
            else:
                dialogs.sort(key=lambda x: x[sort_key])
            
            # Кешируем результаты, если используется кеширование
            if self.use_cache and self.db_handler:
                me = await self.client.get_me()
                account_id = str(me.phone) if me.phone else me.username
                
                # Создаем копию списка без объекта entity, который нельзя сериализовать
                dialogs_to_cache = []
                for dialog in dialogs:
                    dialog_copy = dialog.copy()
                    if 'entity' in dialog_copy:
                        del dialog_copy['entity']
                    dialogs_to_cache.append(dialog_copy)
                
                await self.db_handler.cache_dialogs(dialogs_to_cache, account_id)
            
            return dialogs
        except Exception as e:
            self.log(f"Ошибка при фильтрации диалогов: {e}")
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

    async def close(self):
        """Закрытие подключений"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        
        if self.db_handler:
            await self.db_handler.close() 