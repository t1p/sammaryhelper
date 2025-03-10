from telethon import TelegramClient
from telethon.tl.types import Channel, User
from telethon.tl import functions
import os
from typing import List, Dict, Any
from .db_handler import DatabaseHandler
import datetime

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

    async def get_topics(self, chat_id: int) -> List[Dict[str, Any]]:
        """Получение списка тем в супергруппе, если они поддерживаются"""
        try:
            self.log(f"Получение списка тем для чата {chat_id}")
            
            # Проверяем, является ли чат супергруппой с поддержкой тем
            entity = await self.client.get_entity(chat_id)
            
            # Выводим подробную информацию о сущности
            self.log(f"Информация о чате: type={type(entity).__name__}, id={entity.id}")
            if hasattr(entity, 'forum'):
                self.log(f"Атрибут forum: {entity.forum}")
            else:
                self.log("Атрибут forum отсутствует")
            
            # Проверяем атрибут forum
            is_forum = hasattr(entity, 'forum') and entity.forum
            self.log(f"Чат является форумом: {is_forum}")
            
            if not is_forum:
                self.log(f"Чат {chat_id} не поддерживает темы (атрибут forum отсутствует или False)")
                return []
            
            self.log(f"Пробуем получить темы форума через API...")
            
            # Попробуем использовать прямой API-запрос
            try:
                from telethon import functions
                # Пытаемся получить темы через API
                self.log("Использую GetForumTopicsRequest с параметрами")
                try:
                    result = await self.client(functions.channels.GetForumTopicsRequest(
                        channel=entity,
                        limit=100,
                        offset_date=0,
                        offset_id=0,
                        offset_topic=0
                    ))
                    self.log(f"GetForumTopicsRequest успешно выполнен, получено {len(result.topics) if hasattr(result, 'topics') else 0} тем")
                    
                    # Выводим информацию о результате
                    if hasattr(result, 'topics'):
                        self.log(f"Атрибуты первой темы: {dir(result.topics[0])}" if result.topics else "Список тем пуст")
                        
                        topics = []
                        for topic in result.topics:
                            topic_info = {
                                'id': topic.id,
                                'title': topic.title,
                                'icon_color': getattr(topic, 'icon_color', None),
                                'icon_emoji_id': getattr(topic, 'icon_emoji_id', None),
                                'top_message': getattr(topic, 'top_message', None),
                                'unread_count': getattr(topic, 'unread_count', 0),
                                'unread_mentions_count': getattr(topic, 'unread_mentions_count', 0),
                            }
                            topics.append(topic_info)
                            self.log(f"Добавлена тема: {topic_info}")
                        
                        if topics:
                            self.log(f"Получено {len(topics)} тем через API")
                            return topics
                    else:
                        self.log("Результат запроса не содержит атрибут 'topics'")
                except Exception as api_error:
                    self.log(f"Ошибка при использовании GetForumTopicsRequest: {api_error}")
                    import traceback
                    self.log(traceback.format_exc())
            except ImportError:
                self.log("Не удалось импортировать functions из telethon")
            
            # Если API-метод не сработал, пробуем получить темы через анализ сообщений
            self.log("Получение тем через анализ сообщений...")
            
            topics = []
            topic_ids = set()  # Для отслеживания уникальных идентификаторов тем
            
            # Получаем историю сообщений для анализа тем
            message_count = 0
            self.log("Начинаю анализ сообщений для поиска тем...")
            async for msg in self.client.iter_messages(chat_id, limit=100):
                message_count += 1
                
                # Выводим отладочную информацию о сообщении
                self.log(f"Сообщение #{message_count}: id={msg.id}, тип={type(msg).__name__}")
                if hasattr(msg, 'forum_topic'):
                    self.log(f"  forum_topic = {msg.forum_topic}")
                if hasattr(msg, 'reply_to'):
                    self.log(f"  reply_to присутствует: {dir(msg.reply_to)}")
                    if hasattr(msg.reply_to, 'forum_topic'):
                        self.log(f"  reply_to.forum_topic = {msg.reply_to.forum_topic}")
                    if hasattr(msg.reply_to, 'top_msg_id'):
                        self.log(f"  reply_to.top_msg_id = {msg.reply_to.top_msg_id}")
                
                # Проверяем, является ли сообщение началом темы
                if hasattr(msg, 'forum_topic') and msg.forum_topic:
                    self.log(f"Найдено сообщение с forum_topic=True, id={msg.id}")
                    if msg.id not in topic_ids:
                        topic_ids.add(msg.id)
                        
                        title = "Неизвестная тема"
                        if hasattr(msg, 'topic') and msg.topic:
                            if hasattr(msg.topic, 'title'):
                                title = msg.topic.title
                            self.log(f"Информация о теме: {dir(msg.topic)}")
                        
                        topics.append({
                            'id': msg.id,
                            'title': title,
                            'icon_color': getattr(msg, 'icon_color', None) if hasattr(msg, 'topic') else None,
                            'icon_emoji_id': getattr(msg, 'icon_emoji_id', None) if hasattr(msg, 'topic') else None,
                            'top_message': msg.id,
                            'unread_count': 0,
                            'unread_mentions_count': 0,
                        })
                        self.log(f"Добавлена тема из сообщения: id={msg.id}, title={title}")
                
                # Проверяем, относится ли сообщение к теме
                if hasattr(msg, 'reply_to') and hasattr(msg.reply_to, 'forum_topic') and msg.reply_to.forum_topic:
                    if hasattr(msg.reply_to, 'top_msg_id'):
                        topic_id = msg.reply_to.top_msg_id
                        self.log(f"Найдено сообщение, относящееся к теме: id={msg.id}, topic_id={topic_id}")
                        
                        # Если тема еще не в списке, добавляем ее
                        if topic_id not in topic_ids:
                            topic_ids.add(topic_id)
                            
                            # Пытаемся найти оригинальное сообщение темы для получения заголовка
                            title = f"Тема #{topic_id}"
                            try:
                                topic_msg = await self.client.get_messages(chat_id, ids=topic_id)
                                self.log(f"Найдено исходное сообщение темы: {topic_msg}")
                                if topic_msg and hasattr(topic_msg, 'topic') and hasattr(topic_msg.topic, 'title'):
                                    title = topic_msg.topic.title
                                    self.log(f"Получен заголовок темы: {title}")
                            except Exception as e:
                                self.log(f"Ошибка при получении исходного сообщения темы: {e}")
                            
                            topics.append({
                                'id': topic_id,
                                'title': title,
                                'icon_color': None,
                                'icon_emoji_id': None,
                                'top_message': topic_id,
                                'unread_count': 0,
                                'unread_mentions_count': 0,
                            })
                            self.log(f"Добавлена тема из reply_to: id={topic_id}, title={title}")
            
            # Если обычным методом не нашли темы, но это форум, создадим хотя бы общую тему
            if not topics and is_forum:
                self.log("Темы не найдены обычными способами, но чат помечен как форум. Создаю общую тему.")
                topics.append({
                    'id': 1,  # Типичный ID для общей темы
                    'title': "Общая тема",
                    'icon_color': 0,
                    'icon_emoji_id': None,
                    'top_message': None,
                    'unread_count': 0,
                    'unread_mentions_count': 0,
                })
            
            self.log(f"Получено {len(topics)} тем для чата {chat_id}")
            return topics
        except Exception as e:
            self.log(f"Ошибка при получении тем: {e}")
            import traceback
            self.log(traceback.format_exc())
            return []

    async def has_topics(self, chat_id: int) -> bool:
        """Проверка наличия поддержки тем в супергруппе"""
        try:
            entity = await self.client.get_entity(chat_id)
            
            # Проверяем, является ли чат супергруппой
            if hasattr(entity, 'megagroup') and entity.megagroup:
                # Проверяем поддержку форумов
                if hasattr(entity, 'forum') and entity.forum:
                    self.log(f"Чат {chat_id} поддерживает темы (forum=True)")
                    return True
                
                # Проверяем наличие топиков напрямую через API
                try:
                    # Получаем несколько сообщений и проверяем наличие forum_topic
                    messages = []
                    async for msg in self.client.iter_messages(chat_id, limit=10):
                        messages.append(msg)
                    
                    # Проверяем, есть ли в сообщениях признаки тем
                    for msg in messages:
                        # Проверяем, есть ли атрибут forum_topic
                        if hasattr(msg, 'forum_topic') and msg.forum_topic:
                            self.log(f"Чат {chat_id} поддерживает темы (найдено сообщение с forum_topic)")
                            return True
                        
                        # Проверяем, есть ли в reply_to признаки форума
                        if hasattr(msg, 'reply_to') and hasattr(msg.reply_to, 'forum_topic') and msg.reply_to.forum_topic:
                            self.log(f"Чат {chat_id} поддерживает темы (найдено сообщение с reply_to.forum_topic)")
                            return True
                except Exception as e:
                    self.log(f"Ошибка при проверке сообщений для определения тем: {e}")
            
            self.log(f"Чат {chat_id} не поддерживает темы")
            return False
        except Exception as e:
            self.log(f"Ошибка при проверке поддержки тем: {e}")
            return False

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
                        # Применяем фильтр по теме, если указан topic_id
                        if filters.get('topic_id'):
                            # Проверяем, есть ли message_thread_id в сообщении
                            message_thread_id = message.get('message_thread_id')
                            if message_thread_id != filters.get('topic_id'):
                                continue
                            
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
                    
                    # Если найдены сообщения или нет флага topic_id, возвращаем результат
                    # Если есть topic_id и нет сообщений, продолжаем загрузку из API
                    if len(filtered_messages) > 0 or not filters.get('topic_id'):
                        return filtered_messages
                    else:
                        self.log(f"Не найдено кешированных сообщений для темы {filters.get('topic_id')}, загружаем из API")
            
            # Если кеш не используется или данных в кеше нет, получаем данные из Telegram
            self.log(f"Загрузка сообщений из Telegram API с лимитом: {filters.get('limit')}")
            messages = []
            
            # Словарь пользователей для кеширования информации об отправителях
            user_cache = {}
            
            # Если указан topic_id (ID темы), добавляем его в параметры
            # В Telethon тема представлена как reply_to для форумов
            if filters.get('topic_id'):
                topic_id = filters.get('topic_id')
                self.log(f"Запрашиваю сообщения для темы {topic_id}")
                
                # Получаем ID сообщений для данной темы из истории чата
                thread_messages = []
                message_count = 0
                # Увеличиваем лимит в 5 раз для гарантированного получения всех сообщений 
                total_limit = filters.get('limit', 100) * 5  
                
                self.log(f"Сканирую сообщения для поиска темы {topic_id}, лимит: {total_limit}")
                
                # Создаем список сообщений
                all_messages = []
                async for msg in self.client.iter_messages(chat_id, limit=total_limit):
                    message_count += 1
                    all_messages.append(msg)
                
                self.log(f"Получено всего {len(all_messages)} сообщений для анализа")
                
                # Анализируем все сообщения для поиска темы
                for msg in all_messages:
                    # Выводим отладочную информацию для первых 5 сообщений
                    if message_count <= 5:
                        self.log(f"Сообщение #{message_count}: id={msg.id}")
                        if hasattr(msg, 'forum_topic'):
                            self.log(f"  forum_topic = {msg.forum_topic}")
                        if hasattr(msg, 'reply_to'):
                            self.log(f"  reply_to присутствует")
                            if hasattr(msg.reply_to, 'forum_topic'):
                                self.log(f"  reply_to.forum_topic = {msg.reply_to.forum_topic}")
                            if hasattr(msg.reply_to, 'top_msg_id'):
                                self.log(f"  reply_to.top_msg_id = {msg.reply_to.top_msg_id}")
                    
                    # Проверяем, является ли сообщение стартовым для темы
                    if topic_id == msg.id:
                        self.log(f"Найдено стартовое сообщение темы {topic_id}")
                        thread_messages.append(msg)
                        continue
                    
                    # Сначала проверяем, есть ли reply_to
                    if not hasattr(msg, 'reply_to'):
                        continue
                    
                    # Проверяем, есть ли top_msg_id и совпадает ли с ID темы
                    # Если атрибута нет, проверяем reply_to_msg_id
                    if hasattr(msg.reply_to, 'top_msg_id'):
                        if msg.reply_to.top_msg_id == topic_id:
                            thread_messages.append(msg)
                    elif hasattr(msg.reply_to, 'reply_to_msg_id') and msg.reply_to.reply_to_msg_id == topic_id:
                        thread_messages.append(msg)
                    
                    # Проверяем, есть ли forum_topic
                    if hasattr(msg.reply_to, 'forum_topic') and msg.reply_to.forum_topic:
                        # Если это сообщение из темы форума, проверяем, совпадает ли ID темы
                        if getattr(msg, 'topic_id', None) == topic_id:
                            thread_messages.append(msg)
                
                self.log(f"Найдено {len(thread_messages)} сообщений для темы {topic_id} из {message_count} проверенных")
                self.log(f"ID первых 5 сообщений темы: {[msg.id for msg in thread_messages[:5]]}")
                self.log(f"ID последних 5 сообщений темы: {[msg.id for msg in thread_messages[-5:] if len(thread_messages) >= 5]}")
                
                # Если не удалось найти сообщения по теме, используем все сообщения
                if not thread_messages:
                    self.log(f"Не найдено сообщений для темы {topic_id}, возвращаю все сообщения")
                    # Получаем все сообщения и проверяем, есть ли вообще сообщения с forum_topic
                    has_any_forum_topics = False
                    async for msg in self.client.iter_messages(chat_id, limit=10):
                        if hasattr(msg, 'reply_to') and hasattr(msg.reply_to, 'forum_topic') and msg.reply_to.forum_topic:
                            has_any_forum_topics = True
                            self.log(f"Найдено сообщение с reply_to.forum_topic=True, id={msg.id}")
                            break
                    
                    if has_any_forum_topics:
                        self.log("В чате есть сообщения с forum_topic, но не найдены для данной темы")
                    else:
                        self.log("В чате нет сообщений с forum_topic")
                    
                    # Получаем обычные сообщения, если не удалось найти по теме
                    async for msg in self.client.iter_messages(chat_id, limit=filters.get('limit', 100)):
                        thread_messages.append(msg)
                    
                    self.log(f"Вместо сообщений темы возвращаю {len(thread_messages)} обычных сообщений")
                
                messages = []
                processed_count = 0
                
                # Для устранения проблемы с последними двумя сообщениями
                # 1. Не ограничиваем количество сообщений при обработке
                # 2. Выводим подробную информацию о процессе
                
                for message in thread_messages:
                    processed_count += 1
                    # Раньше мы пропускали сообщения, если достигнут лимит, теперь обрабатываем все
                    # if len(messages) >= filters.get('limit', 100):
                    #    break
                    
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
                    
                    # Применяем фильтр по тексту
                    if filters.get('search') and filters.get('search').lower() not in (message.text or '').lower():
                        continue
                    
                    message_data = {
                        'id': message.id,
                        'text': message.text or '',
                        'date': date_str,  # Используем строку вместо объекта datetime
                        'date_obj': message_date,  # Временный объект datetime для сортировки и т.д.
                        'sender_id': sender_id,
                        'sender_name': sender_name,
                        'photo': bool(message.photo),
                        'video': bool(message.video),
                        'message_thread_id': topic_id  # Сохраняем ID темы
                    }
                    
                    messages.append(message_data)
                
                # Теперь ограничиваем количество сообщений после обработки всех
                user_limit = filters.get('limit', 100)
                if len(messages) > user_limit:
                    self.log(f"Ограничиваем количество сообщений до {user_limit} (было {len(messages)})")
                    messages = messages[:user_limit]
                
                self.log(f"Обработано {processed_count} из {len(thread_messages)} сообщений темы")
                self.log(f"После применения фильтров получено {len(messages)} сообщений для темы {topic_id}")
                self.log(f"ID первых 5 сообщений: {[msg['id'] for msg in messages[:5]]}")
                self.log(f"ID последних 5 сообщений: {[msg['id'] for msg in messages[-5:] if len(messages) >= 5]}")
                
                # Кешируем результаты, если используется кеширование
                if self.use_cache and self.db_handler and messages:
                    # Создаем копию списка для кеширования
                    messages_to_cache = []
                    for message in messages:
                        message_copy = message.copy()
                        # Удаляем временное поле с объектом datetime
                        if 'date_obj' in message_copy:
                            del message_copy['date_obj']
                        messages_to_cache.append(message_copy)
                    
                    try:
                        self.log(f"Кеширование {len(messages_to_cache)} сообщений темы")
                        await self.db_handler.cache_messages(messages_to_cache, chat_id, account_id)
                    except Exception as e:
                        self.log(f"Ошибка при кешировании сообщений: {e}")
                
                # Восстанавливаем объекты datetime для каждого сообщения в возвращаемом списке
                for message in messages:
                    if 'date_obj' in message:
                        message['date'] = message['date_obj']
                        del message['date_obj']
                
                return messages
            
            # Если тема не указана, получаем обычные сообщения
            self.log(f"Загружаю обычные сообщения без указания темы, лимит: {filters.get('limit')}")
            
            # Параметры для iter_messages
            iter_params = {
                'limit': filters.get('limit'),
                'search': filters.get('search')
            }
            
            messages = []
            async for message in self.client.iter_messages(chat_id, **iter_params):
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
                    'video': bool(message.video),
                    'message_thread_id': getattr(message, 'message_thread_id', None)  # Добавляем ID темы, если есть
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