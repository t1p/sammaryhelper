from telethon.tl.types import Channel, User
from telethon.tl import functions
from typing import List, Dict, Any
import datetime
import traceback
from .telegram_client_base import TelegramClientBase

class TelegramClientMessages(TelegramClientBase):
    """Класс для работы с сообщениями в Telegram API"""
    
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

    async def get_messages(self, chat_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получить сообщения из указанного чата.
        """
        self.log(f"Получение сообщений из чата {chat_id}, лимит: {limit}")
        
        if not self.client.is_connected():
            try:
                self.log("Клиент не подключен, подключаюсь...")
                await self.client.connect()
            except Exception as e:
                self.log(f"Ошибка при подключении клиента: {e}")
                return []
        
        messages = []
        try:
            chat = await self.client.get_entity(chat_id)
            async for message in self.client.iter_messages(chat, limit=limit):
                message_data = {
                    'id': message.id,
                    'date': message.date.strftime('%Y-%m-%d %H:%M:%S'),
                    'text': message.text or '',
                    'photo': bool(message.photo),
                    'video': bool(message.video),
                    'sender_id': message.sender_id if message.sender else None,
                    'sender_name': '',
                }
                
                # Получить информацию об отправителе
                if message.sender:
                    if hasattr(message.sender, 'first_name'):
                        message_data['sender_name'] = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()
                    elif hasattr(message.sender, 'title'):
                        message_data['sender_name'] = message.sender.title
                
                # Проверка наличия message_thread_id для тем супергрупп
                if hasattr(message, 'reply_to') and hasattr(message.reply_to, 'forum_topic') and hasattr(message.reply_to.forum_topic, 'id'):
                    message_data['message_thread_id'] = message.reply_to.forum_topic.id
                
                messages.append(message_data)
                
                if len(messages) % 50 == 0:
                    self.log(f"Загружено {len(messages)} сообщений...")
                    
        except Exception as e:
            self.log(f"Ошибка при получении сообщений: {e}")
        
        self.log(f"Загружено {len(messages)} сообщений")
        return messages

    async def get_raw_messages(self, chat_id: int, limit: int = 100) -> List[Any]:
        """
        Получить необработанные объекты сообщений из Telethon API.
        Это даёт доступ ко всей информации о сообщении, включая reply_to.
        """
        self.log(f"Получение raw-сообщений из чата {chat_id}, лимит: {limit}")
        
        if not self.client.is_connected():
            try:
                self.log("Клиент не подключен, подключаюсь...")
                await self.client.connect()
            except Exception as e:
                self.log(f"Ошибка при подключении клиента: {e}")
                return []
        
        raw_messages = []
        try:
            chat = await self.client.get_entity(chat_id)
            async for message in self.client.iter_messages(chat, limit=limit):
                raw_messages.append(message)
                
                if len(raw_messages) % 50 == 0:
                    self.log(f"Загружено {len(raw_messages)} raw-сообщений...")
                    
        except Exception as e:
            self.log(f"Ошибка при получении raw-сообщений: {e}")
        
        self.log(f"Загружено {len(raw_messages)} raw-сообщений")
        return raw_messages