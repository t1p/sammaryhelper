from telethon import TelegramClient
from telethon.tl.types import Channel, User
from telethon.tl import functions
import os
from typing import List, Dict, Any
from .db_handler import DatabaseHandler
import datetime
import json
import sys
import importlib

class TelegramClientManager:
    def __init__(self, settings):
        """Инициализация менеджера клиента Telegram.
        
        Args:
            settings (dict): Словарь с настройками клиента
        """
        self.config_name = settings.get('config_name', None)
        self.app_dir = settings.get('app_dir', None)
        self.debug = settings.get('debug', False)
        self.system_version = settings.get('system_version', 'Windows 10')
        self.device_model = settings.get('device_model', 'PC')
        self.app_version = settings.get('app_version', '1.0.0')
        self.config_format = settings.get('config_format', 'json')
        self.configs_in_parent_dir = settings.get('configs_in_parent_dir', True)  # Добавляем флаг
        
        self.dialogs_cache = {}
        self.client = None
        self.is_ready = False
        
        # Инициализация обработчика базы данных
        self.db_handler = None
        self.use_cache = settings.get('use_cache', True)
        
    def log(self, message):
        """Логирование сообщений"""
        if self.debug:
            print(message)  # Выводим в консоль только если включен режим отладки

    async def init_client(self):
        """Инициализация клиента Telegram."""
        try:
            if self.debug:
                print(f"Инициализация клиента: {self.config_name}")
            
            # Определяем базовую директорию для конфигов
            if self.configs_in_parent_dir:
                configs_base_dir = os.path.dirname(self.app_dir)
            else:
                configs_base_dir = self.app_dir
            
            # Проверяем формат конфигурации
            if self.config_format == 'json':
                # Загружаем JSON-файл
                config_path = os.path.join(configs_base_dir, "configs", f"{self.config_name}.json")
                
                # Пробуем найти файл с расширением .py, если .json не найден
                if not os.path.exists(config_path):
                    py_config_path = os.path.join(configs_base_dir, "configs", f"{self.config_name}.py")
                    if os.path.exists(py_config_path):
                        self.log(f"JSON конфиг не найден, но найден Python-модуль: {py_config_path}")
                        self.config_format = 'py'  # Переключаемся на формат Python
                    else:
                        raise FileNotFoundError(f"Файл конфига не найден: {config_path}")
            
            # Если формат конфига JSON
            if self.config_format == 'json':
                config_path = os.path.join(configs_base_dir, "configs", f"{self.config_name}.json")
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Извлекаем необходимые параметры
                api_id = config.get('api_id')
                api_hash = config.get('api_hash')
                use_proxy = config.get('use_proxy', False)
                proxy_settings = config.get('proxy_settings', {})
                self.openai_api_key = config.get('openai_api_key', '')
                
            else:
                # Загружаем Python-модуль
                config_path = os.path.join(configs_base_dir, "configs", f"{self.config_name}.py")
                
                # Добавляем папку с конфигами в путь импорта
                sys.path.insert(0, os.path.join(configs_base_dir, "configs"))
                
                # Загружаем модуль конфигурации
                config = importlib.import_module(self.config_name)
                
                # Извлекаем необходимые параметры
                api_id = getattr(config, 'api_id', None)
                api_hash = getattr(config, 'api_hash', None)
                use_proxy = getattr(config, 'use_proxy', False)
                proxy_settings = getattr(config, 'proxy_settings', {})
                self.openai_api_key = getattr(config, 'openai_api_key', None)
                
                # Удаляем путь из путей импорта
                sys.path.pop(0)
            
            # Создаем директорию для сессий
            sessions_dir = os.path.join(self.app_dir, "sessions")
            os.makedirs(sessions_dir, exist_ok=True)
            session_name = os.path.join(sessions_dir, self.config_name)

            # Настройки прокси
            proxy = None
            if use_proxy and proxy_settings:
                proxy = (
                    proxy_settings['proxy_type'],
                    proxy_settings['proxy_host'],
                    proxy_settings['proxy_port']
                )

            # Создаем клиент с указанными параметрами версии
            self.client = TelegramClient(
                session_name,
                api_id,
                api_hash,
                proxy=proxy,
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
                    self.db_handler = DatabaseHandler(debug=self.debug)
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
            # Проверяем, что chat_id - это число
            if not isinstance(chat_id, int):
                raise ValueError(f"Некорректный ID диалога: {chat_id}")
            
            self.log(f"Фильтрация сообщений для диалога {chat_id} с фильтрами: {filters}")
            
            # Получаем аккаунт ID
            me = await self.client.get_me()
            account_id = str(me.phone) if me.phone else str(me.id)
            
            # Проверяем кеш
            use_cache = self.use_cache and self.db_handler and not filters.get('force_refresh')
            if use_cache:
                # Проверяем, можно ли использовать кеш
                cached_messages = await self.db_handler.get_cached_messages(chat_id, account_id)
                if cached_messages:
                    self.log(f"Найдено {len(cached_messages)} кешированных сообщений")
                    
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
                    
                    self.log(f"После применения фильтров осталось {len(filtered_messages)} кешированных сообщений")
                    return filtered_messages
            
            # Если кеш не используется или данных в кеше нет, получаем данные из Telegram
            self.log(f"Загрузка сообщений из Telegram API с лимитом: {filters.get('limit')}")
            messages = []
            
            # Словарь пользователей для кеширования информации об отправителях
            user_cache = {}
            
            async for message in self.client.iter_messages(chat_id, search=filters.get('search'), limit=filters.get('limit')):
                sender_name = "Неизвестно"
                sender_id = message.sender_id
                
                if sender_id:
                    # Проверяем, есть ли информация о пользователе в кеше
                    if sender_id in user_cache:
                        sender_name = user_cache[sender_id]
                    else:
                        try:
                            sender = await self.client.get_entity(sender_id)
                            if isinstance(sender, User):
                                sender_name = getattr(sender, 'username', sender.first_name or 'Неизвестно')
                            elif isinstance(sender, Channel):
                                sender_name = sender.title
                            
                            # Кешируем результат
                            user_cache[sender_id] = sender_name
                        except Exception as e:
                            if 'wait of' in str(e).lower() and 'seconds is required' in str(e).lower():
                                # Если требуется ожидание, используем default имя и продолжаем
                                self.log(f"Лимит API на получение информации о пользователе {sender_id}, используем имя по умолчанию")
                            else:
                                self.log(f"Ошибка при получении отправителя: {e}")
                
                # Преобразуем date в строку ISO для безопасной сериализации
                message_date = message.date
                date_str = message_date.isoformat() if isinstance(message_date, datetime.datetime) else str(message_date)
                
                # Применяем фильтр по типу медиа
                if filters.get('filter') == 'photo' and not message.photo:
                    continue
                if filters.get('filter') == 'video' and not message.video:
                    continue
                
                message_data = {
                    'id': message.id,
                    'text': message.text or '',
                    'date': date_str,  # Используем строку вместо объекта datetime
                    'date_obj': message_date,  # Временный объект datetime для сортировки и т.д.
                    'sender_id': sender_id,
                    'sender_name': sender_name,
                    'photo': bool(message.photo),
                    'video': bool(message.video)
                }
                
                messages.append(message_data)
            
            self.log(f"Получено {len(messages)} сообщений из Telegram API")
            
            # Кешируем результаты, если используется кеширование
            if self.use_cache and self.db_handler:
                # Создаем копию списка для кеширования
                messages_to_cache = []
                for message in messages:
                    message_copy = message.copy()
                    # Удаляем временное поле с объектом datetime
                    if 'date_obj' in message_copy:
                        del message_copy['date_obj']
                    messages_to_cache.append(message_copy)
                
                try:
                    self.log(f"Кеширование {len(messages_to_cache)} сообщений")
                    await self.db_handler.cache_messages(messages_to_cache, chat_id, account_id)
                except Exception as e:
                    self.log(f"Ошибка при кешировании сообщений: {e}")
            
            # Восстанавливаем объекты datetime для каждого сообщения в возвращаемом списке
            for message in messages:
                if 'date_obj' in message:
                    message['date'] = message['date_obj']
                    del message['date_obj']
            
            return messages
        except Exception as e:
            self.log(f"Ошибка при фильтрации сообщений: {e}")
            import traceback
            self.log(traceback.format_exc())
            raise Exception(f"Ошибка при фильтрации сообщений: {e}")

    async def filter_dialogs(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Фильтрация диалогов по заданным критериям"""
        try:
            self.log(f"Вызов filter_dialogs с фильтрами: {filters}")
            
            # Проверяем лимит
            limit = filters.get('limit')
            search_query = filters.get('search', '')
            force_refresh = filters.get('force_refresh', False)
            
            self.log(f"Полученный лимит для диалогов: {limit}, поиск: '{search_query}', обновление: {force_refresh}")
            
            # Получаем ID аккаунта
            me = await self.client.get_me()
            account_id = str(me.phone) if me.phone else me.username
            self.log(f"ID аккаунта: {account_id}")
            
            # Используем кеш для получения данных только если не требуется обновление
            dialogs = []
            use_cache = self.use_cache and self.db_handler
            
            if use_cache:
                # Загружаем диалоги из кеша
                cached_dialogs = await self.db_handler.get_cached_dialogs(account_id, limit)
                self.log(f"Получено {len(cached_dialogs)} кешированных диалогов из БД")
                
                # Определяем, нужно ли обновление кеша
                # Обновляемся ТОЛЬКО если:
                # 1. Явно запрошено обновление (force_refresh)
                # 2. Кеш пуст или недостаточен И поисковый запрос пустой
                update_cache = force_refresh or (len(cached_dialogs) < limit and not search_query)
                
                if update_cache:
                    self.log(f"Обновление кеша диалогов (force_refresh: {force_refresh}, cache_size: {len(cached_dialogs)}, limit: {limit})")
                    api_dialogs = []
                    
                    # Загружаем диалоги из Telegram API
                    async for dialog in self.client.iter_dialogs(limit=limit):
                        dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
                        
                        api_dialogs.append({
                            'id': dialog.id,
                            'name': dialog.name,
                            'type': dialog_type,
                            'entity': dialog.entity,
                            'folder_id': dialog.folder_id,
                            'unread_count': dialog.unread_count
                        })
                    
                    self.log(f"Получено {len(api_dialogs)} диалогов из Telegram API")
                    
                    # Кешируем диалоги из API
                    dialogs_to_cache = []
                    for dialog in api_dialogs:
                        dialog_copy = dialog.copy()
                        if 'entity' in dialog_copy:
                            del dialog_copy['entity']
                        dialogs_to_cache.append(dialog_copy)
                    
                    self.log(f"Кеширование {len(dialogs_to_cache)} диалогов в БД")
                    await self.db_handler.cache_dialogs(dialogs_to_cache, account_id)
                    
                    # Объединяем с кешированными диалогами
                    merged_dialogs = {}
                    
                    # Сначала добавляем диалоги из API
                    for dialog in api_dialogs:
                        merged_dialogs[dialog['id']] = dialog
                    
                    # Затем добавляем остальные из кеша, если их нет в результате API и не превышен лимит
                    for dialog in cached_dialogs:
                        if dialog['id'] not in merged_dialogs and len(merged_dialogs) < limit:
                            merged_dialogs[dialog['id']] = dialog
                    
                    # Преобразуем обратно в список
                    dialogs = list(merged_dialogs.values())
                else:
                    # Используем только кешированные данные для поиска
                    self.log(f"Используем только кешированные диалоги для поиска '{search_query}'")
                    dialogs = cached_dialogs
            else:
                # Если кеш отключен, загружаем данные только из Telegram API
                self.log(f"Кеш отключен, загружаем диалоги из Telegram API с лимитом: {limit}")
                async for dialog in self.client.iter_dialogs(limit=limit):
                    dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
                    
                    dialogs.append({
                        'id': dialog.id,
                        'name': dialog.name,
                        'type': dialog_type,
                        'entity': dialog.entity,
                        'folder_id': dialog.folder_id,
                        'unread_count': dialog.unread_count
                    })
                
                self.log(f"Получено {len(dialogs)} диалогов из Telegram API")
            
            # Применяем фильтр по имени ко всем полученным диалогам
            self.log(f"Общее количество полученных диалогов до фильтрации: {len(dialogs)}")
            filtered_dialogs = []
            
            if search_query:
                for dialog in dialogs:
                    if search_query.lower() in dialog['name'].lower():
                        filtered_dialogs.append(dialog)
                self.log(f"После фильтрации по поиску '{search_query}' осталось {len(filtered_dialogs)} диалогов")
            else:
                filtered_dialogs = dialogs
                self.log(f"Поиск не применялся, всего диалогов: {len(filtered_dialogs)}")
            
            # Сортировка
            sort_key = filters.get('sort', 'name')
            if sort_key == 'folder':
                filtered_dialogs.sort(key=lambda x: x['folder_id'] if x['folder_id'] is not None else -1)
            else:
                filtered_dialogs.sort(key=lambda x: x[sort_key])
            
            return filtered_dialogs
        except Exception as e:
            self.log(f"Ошибка при фильтрации диалогов: {e}")
            import traceback
            self.log(traceback.format_exc())
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