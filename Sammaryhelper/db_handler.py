import os
import json
import asyncio
import datetime
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    print("ВНИМАНИЕ: Модуль asyncpg не установлен. Кеширование в PostgreSQL недоступно.")
    print("Для установки выполните: pip install asyncpg")

from typing import Dict, List, Any, Optional, Tuple

# Кастомный JSONEncoder для обработки datetime
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)

class DatabaseHandler:
    """Класс для работы с базой данных PostgreSQL"""
    
    def __init__(self, config_name: str = None, app_dir: str = None, debug: bool = False):
        """Инициализация обработчика базы данных"""
        self.connection_pool = None
        self.debug = debug
        self.app_dir = app_dir or os.path.dirname(os.path.abspath(__file__))
        self.config_name = config_name or 'config_0707'  # Используем имя конфига по умолчанию
        self.config = self._load_config()
        
    def log(self, message):
        """Логирование сообщений"""
        if self.debug:
            print(f"[DB] {message}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации подключения к БД из основного конфига"""
        try:
            # Загружаем основной конфиг
            config_path = os.path.join(self.app_dir, "configs", f"{self.config_name}.py")
            if os.path.exists(config_path):
                # Импортируем модуль конфигурации
                import importlib.util
                spec = importlib.util.spec_from_file_location("config", config_path)
                config = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config)
                
                # Проверяем, есть ли настройки базы данных в конфиге
                if hasattr(config, 'db_settings'):
                    self.log(f"Загружены настройки БД из конфига: {config_path}")
                    return config.db_settings
                else:
                    self.log(f"В конфиге отсутствуют настройки БД, используем настройки по умолчанию")
            else:
                self.log(f"Файл конфига не найден: {config_path}")
            
            # Если не удалось загрузить настройки, возвращаем значения по умолчанию
            return {
                "host": "localhost",
                "port": 5432,
                "database": "telegram_summarizer",
                "user": "postgres",
                "password": "postgres"
            }
        except Exception as e:
            self.log(f"Ошибка при загрузке конфигурации БД: {e}")
            return {
                "host": "localhost",
                "port": 5432,
                "database": "telegram_summarizer",
                "user": "postgres",
                "password": "postgres"
            }
    
    async def init_connection(self) -> bool:
        """Инициализация подключения к базе данных"""
        if not ASYNCPG_AVAILABLE:
            self.log("Модуль asyncpg не установлен. Кеширование в PostgreSQL недоступно.")
            return False
            
        try:
            self.log(f"Подключение к базе данных: {self.config.get('host')}:{self.config.get('port')}/{self.config.get('database')}")
            self.connection_pool = await asyncpg.create_pool(
                host=self.config.get("host"),
                port=self.config.get("port"),
                database=self.config.get("database"),
                user=self.config.get("user"),
                password=self.config.get("password")
            )
            
            self.log("Подключение к базе данных успешно установлено")
            
            # Создаем таблицы, если они не существуют
            await self._create_tables()
            return True
        except Exception as e:
            self.log(f"Ошибка при подключении к базе данных: {e}")
            return False
    
    async def _create_tables(self):
        """Создание необходимых таблиц в базе данных"""
        async with self.connection_pool.acquire() as connection:
            # Таблица для кеширования диалогов
            await connection.execute('''
                CREATE TABLE IF NOT EXISTS dialogs (
                    id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    folder_id INTEGER,
                    account_id TEXT NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            ''')
            
            # Проверяем, существует ли колонка message_thread_id в таблице messages
            column_exists = False
            try:
                # Проверяем наличие колонки в таблице
                column_check = await connection.fetchval('''
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'messages' AND column_name = 'message_thread_id'
                ''')
                column_exists = column_check is not None
                self.log(f"Проверка наличия колонки message_thread_id: {column_exists}")
            except Exception as e:
                self.log(f"Ошибка при проверке колонки message_thread_id: {e}")
            
            # Если таблица messages не существует, создаем её с нужной структурой
            if not column_exists:
                # Пересоздаем таблицу messages с нужной колонкой если она не существует
                self.log("Создаем или обновляем таблицу messages с колонкой message_thread_id")
                
                # Сначала проверяем, существует ли таблица messages
                table_exists = await connection.fetchval('''
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'messages'
                    )
                ''')
                
                if table_exists:
                    self.log("Таблица messages существует, добавляем колонку message_thread_id")
                    # Если таблица существует, пробуем добавить колонку
                    try:
                        await connection.execute('ALTER TABLE messages ADD COLUMN message_thread_id BIGINT')
                        self.log("Колонка message_thread_id успешно добавлена")
                    except Exception as e:
                        self.log(f"Не удалось добавить колонку message_thread_id: {e}")
                else:
                    # Таблица не существует, создаем с нужной структурой
                    self.log("Таблица messages не существует, создаем новую")
                    await connection.execute('''
                        CREATE TABLE messages (
                            id BIGINT NOT NULL,
                            dialog_id BIGINT NOT NULL,
                            sender_id BIGINT,
                            sender_name TEXT,
                            text TEXT,
                            date TIMESTAMP NOT NULL,
                            account_id TEXT NOT NULL,
                            message_thread_id BIGINT,
                            data JSONB NOT NULL,
                            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (id, dialog_id)
                        )
                    ''')
            else:
                self.log("Колонка message_thread_id уже существует в таблице messages")
            
            # Таблица для кеширования тем
            await connection.execute('''
                CREATE TABLE IF NOT EXISTS topics (
                    id BIGINT NOT NULL,
                    dialog_id BIGINT NOT NULL,
                    title TEXT NOT NULL,
                    icon_color INTEGER,
                    icon_emoji_id BIGINT,
                    unread_count INTEGER DEFAULT 0,
                    unread_mentions_count INTEGER DEFAULT 0,
                    account_id TEXT NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (id, dialog_id)
                )
            ''')
            
            # Таблица для кеширования запросов к ИИ
            await connection.execute('''
                CREATE TABLE IF NOT EXISTS ai_requests (
                    id SERIAL PRIMARY KEY,
                    user_query TEXT NOT NULL,
                    context TEXT,
                    model TEXT NOT NULL,
                    system_prompt TEXT,
                    account_id TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            ''')
            
            # Таблица для кеширования ответов ИИ
            await connection.execute('''
                CREATE TABLE IF NOT EXISTS ai_responses (
                    id SERIAL PRIMARY KEY,
                    request_id INTEGER NOT NULL REFERENCES ai_requests(id),
                    response TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE (request_id)
                )
            ''')
    
    async def cache_dialogs(self, dialogs: List[Dict[str, Any]], account_id: str) -> bool:
        """Кеширование списка диалогов"""
        try:
            self.log(f"Кеширование {len(dialogs)} диалогов для аккаунта {account_id}")
            async with self.connection_pool.acquire() as connection:
                async with connection.transaction():
                    for dialog in dialogs:
                        self.log(f"Кеширование диалога: {dialog['name']} (ID: {dialog['id']})")
                        await connection.execute('''
                            INSERT INTO dialogs (id, name, type, folder_id, account_id, data)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT (id) 
                            DO UPDATE SET 
                                name = $2,
                                type = $3,
                                folder_id = $4,
                                data = $6,
                                updated_at = NOW()
                        ''', 
                        dialog['id'], 
                        dialog['name'], 
                        dialog['type'], 
                        dialog.get('folder_id'), 
                        account_id,
                        json.dumps(dialog))
            self.log(f"Кеширование диалогов завершено успешно")
            return True
        except Exception as e:
            self.log(f"Ошибка при кешировании диалогов: {e}")
            return False
    
    async def get_cached_dialogs(self, account_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """Получение кешированных диалогов"""
        try:
            self.log(f"Получение кешированных диалогов для аккаунта {account_id}, лимит: {limit}")
            async with self.connection_pool.acquire() as connection:
                # Добавляем LIMIT в SQL-запрос, если limit задан
                query = '''
                    SELECT data FROM dialogs 
                    WHERE account_id = $1
                    ORDER BY updated_at DESC
                '''
                
                # Добавляем ограничение, если указан limit
                if limit:
                    query += f" LIMIT {limit}"
                    self.log(f"SQL запрос с лимитом {limit}: {query}")
                else:
                    self.log(f"SQL запрос без лимита: {query}")
                    
                rows = await connection.fetch(query, account_id)
                
                result = [json.loads(row['data']) for row in rows]
                self.log(f"Получено {len(result)} кешированных диалогов из БД")
                return result
        except Exception as e:
            self.log(f"Ошибка при получении кешированных диалогов: {e}")
            return []
    
    async def cache_messages(self, messages: List[Dict[str, Any]], dialog_id: int, account_id: str) -> bool:
        """Кеширование сообщений диалога"""
        try:
            self.log(f"Кеширование {len(messages)} сообщений для диалога {dialog_id}")
            
            # Проверяем наличие колонки message_thread_id
            column_exists = False
            async with self.connection_pool.acquire() as connection:
                try:
                    column_check = await connection.fetchval('''
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'messages' AND column_name = 'message_thread_id'
                    ''')
                    column_exists = column_check is not None
                    self.log(f"Проверка наличия колонки message_thread_id для кеширования: {column_exists}")
                except Exception as e:
                    self.log(f"Ошибка при проверке колонки message_thread_id: {e}")
                
                async with connection.transaction():
                    for message in messages:
                        # Преобразуем данные в строку JSON с поддержкой datetime
                        data_json = json.dumps(message, cls=DateTimeEncoder, ensure_ascii=False)
                        
                        # Преобразуем строковую дату в datetime объект, если это строка
                        message_date = message.get('date')
                        if isinstance(message_date, str):
                            try:
                                # Пробуем распарсить ISO формат с часовым поясом
                                if '+' in message_date or 'Z' in message_date:
                                    message_date = datetime.datetime.fromisoformat(message_date.replace('Z', '+00:00'))
                                    # Убираем информацию о часовом поясе
                                    message_date = message_date.replace(tzinfo=None)
                                else:
                                    # Простой формат без часового пояса
                                    message_date = datetime.datetime.fromisoformat(message_date)
                            except ValueError:
                                # Если не удалось распарсить, используем текущую дату
                                self.log(f"Не удалось распарсить дату: {message_date}, используем текущую")
                                message_date = datetime.datetime.now()
                        elif isinstance(message_date, datetime.datetime):
                            # Если это уже datetime объект, убедимся что у него нет tzinfo
                            if message_date.tzinfo is not None:
                                message_date = message_date.replace(tzinfo=None)
                        
                        # Если date всё еще не datetime, используем текущее время
                        if not isinstance(message_date, datetime.datetime):
                            message_date = datetime.datetime.now()
                            self.log(f"Дата не является объектом datetime, используем текущую: {message_date}")
                        
                        self.log(f"Дата для сообщения ID {message['id']}: {message_date} (тип: {type(message_date)})")
                        
                        # Получаем ID темы сообщения, если есть
                        message_thread_id = message.get('message_thread_id')
                        
                        if column_exists:
                            # Используем SQL-запрос с колонкой message_thread_id
                            await connection.execute('''
                                INSERT INTO messages (id, dialog_id, sender_id, sender_name, text, date, account_id, message_thread_id, data)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                                ON CONFLICT (id, dialog_id) 
                                DO UPDATE SET 
                                    sender_id = $3,
                                    sender_name = $4,
                                    text = $5,
                                    date = $6,
                                    message_thread_id = $8,
                                    data = $9,
                                    updated_at = NOW()
                            ''', 
                            message['id'], 
                            dialog_id,
                            message.get('sender_id'),
                            message.get('sender_name', 'Неизвестно'),
                            message.get('text', ''),
                            message_date,
                            account_id,
                            message_thread_id,
                            data_json)
                        else:
                            # Используем SQL-запрос без колонки message_thread_id
                            await connection.execute('''
                                INSERT INTO messages (id, dialog_id, sender_id, sender_name, text, date, account_id, data)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                                ON CONFLICT (id, dialog_id) 
                                DO UPDATE SET 
                                    sender_id = $3,
                                    sender_name = $4,
                                    text = $5,
                                    date = $6,
                                    data = $8,
                                    updated_at = NOW()
                            ''', 
                            message['id'], 
                            dialog_id,
                            message.get('sender_id'),
                            message.get('sender_name', 'Неизвестно'),
                            message.get('text', ''),
                            message_date,
                            account_id,
                            data_json)
            
            self.log(f"Сообщения успешно кешированы")
            return True
        except Exception as e:
            self.log(f"Ошибка при кешировании сообщений: {e}")
            import traceback
            self.log(traceback.format_exc())
            return False
    
    async def get_cached_messages(self, dialog_id: int, account_id: str) -> List[Dict[str, Any]]:
        """Получение кешированных сообщений диалога"""
        try:
            self.log(f"Получение кешированных сообщений для диалога {dialog_id}")
            async with self.connection_pool.acquire() as connection:
                rows = await connection.fetch('''
                    SELECT data FROM messages 
                    WHERE dialog_id = $1 AND account_id = $2
                    ORDER BY date DESC
                ''', dialog_id, account_id)
                
                result = [json.loads(row['data']) for row in rows]
                self.log(f"Получено {len(result)} кешированных сообщений")
                return result
        except Exception as e:
            self.log(f"Ошибка при получении кешированных сообщений: {e}")
            return []
    
    async def cache_topics(self, topics: List[Dict[str, Any]], dialog_id: int, account_id: str) -> bool:
        """Кеширование тем для супергруппы"""
        try:
            self.log(f"Кеширование {len(topics)} тем для диалога {dialog_id}")
            async with self.connection_pool.acquire() as connection:
                async with connection.transaction():
                    for topic in topics:
                        # Преобразуем данные в строку JSON
                        data_json = json.dumps(topic, cls=DateTimeEncoder, ensure_ascii=False)
                        
                        await connection.execute('''
                            INSERT INTO topics (id, dialog_id, title, icon_color, icon_emoji_id, unread_count, unread_mentions_count, account_id, data)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ON CONFLICT (id, dialog_id) 
                            DO UPDATE SET 
                                title = $3,
                                icon_color = $4,
                                icon_emoji_id = $5,
                                unread_count = $6,
                                unread_mentions_count = $7,
                                data = $9,
                                updated_at = NOW()
                        ''', 
                        topic['id'], 
                        dialog_id,
                        topic['title'],
                        topic.get('icon_color'),
                        topic.get('icon_emoji_id'),
                        topic.get('unread_count', 0),
                        topic.get('unread_mentions_count', 0),
                        account_id,
                        data_json)
            self.log(f"Темы успешно кешированы")
            return True
        except Exception as e:
            self.log(f"Ошибка при кешировании тем: {e}")
            import traceback
            self.log(traceback.format_exc())
            return False
            
    async def get_cached_topics(self, dialog_id: int, account_id: str) -> List[Dict[str, Any]]:
        """Получение кешированных тем для супергруппы"""
        try:
            self.log(f"Получение кешированных тем для диалога {dialog_id}")
            async with self.connection_pool.acquire() as connection:
                rows = await connection.fetch('''
                    SELECT data FROM topics 
                    WHERE dialog_id = $1 AND account_id = $2
                    ORDER BY id
                ''', dialog_id, account_id)
                
                result = [json.loads(row['data']) for row in rows]
                self.log(f"Получено {len(result)} кешированных тем")
                return result
        except Exception as e:
            self.log(f"Ошибка при получении кешированных тем: {e}")
            import traceback
            self.log(traceback.format_exc())
            return []
            
    async def get_cached_messages_by_topic(self, dialog_id: int, topic_id: int, account_id: str) -> List[Dict[str, Any]]:
        """Получение кешированных сообщений по теме"""
        try:
            self.log(f"Получение кешированных сообщений для темы {topic_id} в диалоге {dialog_id}")
            
            # Проверяем наличие колонки message_thread_id
            async with self.connection_pool.acquire() as connection:
                column_exists = await connection.fetchval('''
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'messages' AND column_name = 'message_thread_id'
                ''')
                
                if not column_exists:
                    self.log("Колонка message_thread_id не существует, возвращаем пустой список")
                    return []
                
                # Если колонка существует, получаем сообщения
                rows = await connection.fetch('''
                    SELECT data FROM messages 
                    WHERE dialog_id = $1 AND account_id = $2 AND message_thread_id = $3
                    ORDER BY date DESC
                ''', dialog_id, account_id, topic_id)
                
                result = [json.loads(row['data']) for row in rows]
                self.log(f"Получено {len(result)} кешированных сообщений для темы")
                return result
                
        except Exception as e:
            self.log(f"Ошибка при получении кешированных сообщений темы: {e}")
            import traceback
            self.log(traceback.format_exc())
            return []
    
    async def cache_ai_interaction(self, user_query: str, context: str, model: str, 
                                  system_prompt: str, response: str, account_id: str) -> bool:
        """Кеширование взаимодействия с ИИ"""
        try:
            async with self.connection_pool.acquire() as connection:
                async with connection.transaction():
                    # Сохраняем запрос
                    request_id = await connection.fetchval('''
                        INSERT INTO ai_requests (user_query, context, model, system_prompt, account_id)
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING id
                    ''', user_query, context, model, system_prompt, account_id)
                    
                    # Сохраняем ответ
                    await connection.execute('''
                        INSERT INTO ai_responses (request_id, response)
                        VALUES ($1, $2)
                    ''', request_id, response)
            return True
        except Exception as e:
            print(f"Ошибка при кешировании взаимодействия с ИИ: {e}")
            return False
    
    async def get_cached_ai_response(self, user_query: str, context: str, model: str, 
                                    system_prompt: str, account_id: str) -> Optional[str]:
        """Получение кешированного ответа ИИ"""
        try:
            async with self.connection_pool.acquire() as connection:
                response = await connection.fetchval('''
                    SELECT r.response FROM ai_responses r
                    JOIN ai_requests q ON r.request_id = q.id
                    WHERE q.user_query = $1 
                    AND q.context = $2 
                    AND q.model = $3 
                    AND q.system_prompt = $4
                    AND q.account_id = $5
                    ORDER BY q.created_at DESC
                    LIMIT 1
                ''', user_query, context, model, system_prompt, account_id)
                
                return response
        except Exception as e:
            print(f"Ошибка при получении кешированного ответа ИИ: {e}")
            return None
    
    async def close(self):
        """Закрытие подключения к базе данных"""
        if self.connection_pool:
            await self.connection_pool.close() 