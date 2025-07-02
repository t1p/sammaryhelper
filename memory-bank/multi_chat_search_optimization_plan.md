# План оптимизации кеширования для поиска по нескольким чатам

## Общий обзор

Данный план описывает необходимые изменения в системе кеширования приложения Sammaryhelper для реализации эффективного поиска сообщений по нескольким чатам одновременно. План учитывает текущую архитектуру БД и предлагает конкретные оптимизации, отсортированные по приоритету.

## 1. Оптимизация транзакций при вставке данных

**Проблема:** Текущая реализация неэффективно обрабатывает вставку большого количества сообщений, выполняя отдельный SQL-запрос для каждого сообщения.

**Решение:**

1. **Пакетное выполнение запросов:**
   ```python
   # Вместо индивидуальных запросов для каждого сообщения
   batch_size = 100
   for i in range(0, len(messages), batch_size):
       batch = messages[i:i+batch_size]
       # Подготовка массового запроса
       values = []
       for message in batch:
           values.append((message['id'], dialog_id, ... # другие поля
           ))
       
       # Выполнение массового запроса
       await connection.executemany('''
           INSERT INTO messages (id, dialog_id, ... другие поля)
           VALUES ($1, $2, ...)
           ON CONFLICT (id, dialog_id) 
           DO UPDATE SET ... 
       ''', values)
   ```

2. **Предварительная обработка данных:**
   * Обработка и преобразование данных перед транзакцией
   * Валидация данных до начала транзакции

3. **Адаптивная подгрузка данных:**
   ```python
   async def get_last_message_date(self, dialog_id: int, account_id: str) -> Optional[datetime.datetime]:
       """Получение даты последнего кешированного сообщения"""
       try:
           async with self.connection_pool.acquire() as connection:
               result = await connection.fetchval('''
                   SELECT MAX(date) FROM messages 
                   WHERE dialog_id = $1 AND account_id = $2
               ''', dialog_id, account_id)
               return result
       except Exception as e:
           self.log(f"Ошибка при получении даты последнего сообщения: {e}")
           return None
   
   # Использование в telegram_client.py
   async def filter_messages(self, chat_id: int, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
       # ...
       if self.use_cache and self.db_handler:
           # Получаем дату последнего сообщения
           last_message_date = await self.db_handler.get_last_message_date(chat_id, account_id)
           
           # Если есть кешированные сообщения, загружаем только новые
           if last_message_date:
               # Запрашиваем только сообщения с даты последнего + 1 секунда
               # Это можно использовать в клиенте Telethon, если он поддерживает фильтрацию по дате
               min_date = last_message_date + datetime.timedelta(seconds=1)
               # Запрашиваем сообщения у API
               new_messages = await self._fetch_messages_after_date(chat_id, min_date, filters)
               # Кешируем новые сообщения
               if new_messages:
                   await self.db_handler.cache_messages(new_messages, chat_id, account_id)
               
               # Получаем все кешированные сообщения, включая новые
               all_messages = await self.db_handler.get_cached_messages(chat_id, account_id)
               return all_messages
   ```

## 2. Добавление полнотекстового поиска

**Проблема:** Отсутствие эффективного механизма полнотекстового поиска по содержимому сообщений.

**Решение:**

1. **Модификация схемы для поддержки полнотекстового поиска:**
   ```sql
   -- Добавление поддержки расширения tsvector
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   
   -- Изменение таблицы messages
   ALTER TABLE messages ADD COLUMN ts_text tsvector 
   GENERATED ALWAYS AS (to_tsvector('russian', text)) STORED;
   
   -- Создание индекса для полнотекстового поиска
   CREATE INDEX messages_ts_text_idx ON messages USING GIN (ts_text);
   ```

2. **Функции для поиска сообщений по тексту:**
   ```python
   async def search_messages_by_text(self, search_query: str, dialog_ids: List[int], account_id: str, 
                                      limit: int = 100) -> List[Dict[str, Any]]:
       try:
           async with self.connection_pool.acquire() as connection:
               # Преобразуем список ID в строку для SQL
               dialog_ids_str = ','.join(str(dialog_id) for dialog_id in dialog_ids)
               
               # SQL запрос с полнотекстовым поиском
               query = f'''
                   SELECT data FROM messages 
                   WHERE account_id = $1 
                   AND dialog_id IN ({dialog_ids_str})
                   AND ts_text @@ plainto_tsquery('russian', $2)
                   ORDER BY date DESC
                   LIMIT $3
               '''
               
               rows = await connection.fetch(query, account_id, search_query, limit)
               result = [json.loads(row['data']) for row in rows]
               return result
       except Exception as e:
           self.log(f"Ошибка при поиске сообщений по тексту: {e}")
           return []
   ```

3. **Поддержка нескольких языков:**
   ```python
   async def detect_language(self, text: str) -> str:
       """Определение языка текста"""
       # Простая эвристика для определения языка
       # В реальном приложении использовать более сложные алгоритмы
       cyrillic_count = sum(1 for c in text if 'а' <= c.lower() <= 'я')
       if cyrillic_count > len(text) * 0.3:
           return 'russian'
       return 'english'
   
   async def prepare_text_for_search(self, text: str) -> str:
       lang = await self.detect_language(text)
       query = f"to_tsvector('{lang}', $1)"
       # Далее использовать query в SQL запросах полнотекстового поиска
   ```

## 3. Оптимизация индексов для поиска

**Проблема:** Отсутствие или неэффективные индексы для часто используемых полей поиска.

**Решение:**

1. **Анализ часто используемых полей для поиска:**
   - sender_name (имя отправителя)
   - date (дата сообщения)
   - message_thread_id (ID темы)
   - dialog_id (ID чата)

2. **Добавление оптимальных индексов:**
   ```sql
   -- Индекс для эффективного поиска по имени отправителя
   CREATE INDEX idx_messages_sender_name ON messages (sender_name);
   
   -- Составной индекс для поиска по диалогу и дате
   CREATE INDEX idx_messages_dialog_date ON messages (dialog_id, date DESC);
   
   -- Индекс для поиска сообщений в теме
   CREATE INDEX idx_messages_thread_id ON messages (message_thread_id);
   
   -- Индекс для поиска по аккаунту и диалогу
   CREATE INDEX idx_messages_account_dialog ON messages (account_id, dialog_id);
   ```

3. **Функция для создания индексов:**
   ```python
   async def create_optimized_indexes(self):
       """Создание оптимизированных индексов для поиска"""
       async with self.connection_pool.acquire() as connection:
           # Проверка существования индексов перед созданием
           existing_indexes = await connection.fetch('''
               SELECT indexname FROM pg_indexes
               WHERE tablename = 'messages'
           ''')
           existing_names = [row['indexname'] for row in existing_indexes]
           
           indexes_to_create = [
               ("idx_messages_sender_name", "CREATE INDEX IF NOT EXISTS idx_messages_sender_name ON messages (sender_name)"),
               ("idx_messages_dialog_date", "CREATE INDEX IF NOT EXISTS idx_messages_dialog_date ON messages (dialog_id, date DESC)"),
               ("idx_messages_thread_id", "CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages (message_thread_id)"),
               ("idx_messages_account_dialog", "CREATE INDEX IF NOT EXISTS idx_messages_account_dialog ON messages (account_id, dialog_id)")
           ]
           
           for index_name, create_cmd in indexes_to_create:
               if index_name not in existing_names:
                   self.log(f"Создание индекса: {index_name}")
                   await connection.execute(create_cmd)
   ```

## 4. Оптимизация работы с датами

**Проблема:** Текущая реализация неэффективно работает с датами, выполняя множество преобразований и проверок.

**Решение:**

1. **Стандартизация формата дат:**
   ```python
   def standardize_date(date_value) -> datetime.datetime:
       """Стандартизация даты для хранения в БД"""
       if isinstance(date_value, str):
           # Поддержка различных форматов ввода
           try:
               if '+' in date_value or 'Z' in date_value:
                   # ISO с часовым поясом
                   date_obj = datetime.datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                   return date_obj.replace(tzinfo=None)
               else:
                   # Стандартные форматы даты
                   for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d'):
                       try:
                           return datetime.datetime.strptime(date_value, fmt)
                       except ValueError:
                           continue
               # Если ничего не подошло, пробуем ISO формат
               return datetime.datetime.fromisoformat(date_value)
           except ValueError:
               return datetime.datetime.now()
       elif isinstance(date_value, datetime.datetime):
           return date_value.replace(tzinfo=None) if date_value.tzinfo else date_value
       else:
           return datetime.datetime.now()
   ```

2. **Диапазоны дат для поиска:**
   ```python
   async def search_messages_by_date_range(self, dialog_ids: List[int], 
                                        start_date: datetime.datetime, 
                                        end_date: datetime.datetime, 
                                        account_id: str) -> List[Dict[str, Any]]:
       """Поиск сообщений в диапазоне дат"""
       try:
           async with self.connection_pool.acquire() as connection:
               # Преобразование списка ID в строку для SQL
               dialog_ids_str = ','.join(str(dialog_id) for dialog_id in dialog_ids)
               
               query = f'''
                   SELECT data FROM messages 
                   WHERE account_id = $1 
                   AND dialog_id IN ({dialog_ids_str})
                   AND date BETWEEN $2 AND $3
                   ORDER BY date DESC
               '''
               
               rows = await connection.fetch(query, account_id, start_date, end_date)
               return [json.loads(row['data']) for row in rows]
       except Exception as e:
           self.log(f"Ошибка при поиске сообщений по дате: {e}")
           return []
   ```

3. **Функция поиска по дате с поддержкой человеческих форматов:**
   ```python
   async def search_messages_by_date_string(self, dialog_ids: List[int], 
                                         date_string: str, 
                                         account_id: str) -> List[Dict[str, Any]]:
       """Поиск сообщений по строковому представлению даты"""
       # Разбор строки даты
       try:
           # Поддержка форматов: "сегодня", "вчера", "2023-12-31", "31.12.2023", и т.д.
           if date_string.lower() == "сегодня":
               today = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
               tomorrow = today + datetime.timedelta(days=1)
               return await self.search_messages_by_date_range(dialog_ids, today, tomorrow, account_id)
           elif date_string.lower() == "вчера":
               yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).replace(
                   hour=0, minute=0, second=0, microsecond=0)
               today = yesterday + datetime.timedelta(days=1)
               return await self.search_messages_by_date_range(dialog_ids, yesterday, today, account_id)
           else:
               # Пытаемся определить формат даты
               date = standardize_date(date_string)
               next_day = date + datetime.timedelta(days=1)
               return await self.search_messages_by_date_range(dialog_ids, date, next_day, account_id)
       except Exception as e:
           self.log(f"Ошибка при разборе строки даты '{date_string}': {e}")
           return []
   ```

## 5. Оптимизация хранения данных

**Проблема:** Неоптимальное хранение данных с дублированием информации в JSONB и отдельных колонках.

**Решение:**

1. **Реструктуризация схемы таблиц:**
   ```sql
   -- Модификация таблицы messages
   CREATE TABLE messages_optimized (
       id BIGINT NOT NULL,
       dialog_id BIGINT NOT NULL,
       sender_id BIGINT,
       sender_name TEXT,
       text TEXT,
       date TIMESTAMP NOT NULL,
       account_id TEXT NOT NULL,
       message_thread_id BIGINT,
       has_reply BOOLEAN,   -- Имеет ли ответы
       reply_to_id BIGINT,  -- Ссылка на сообщение, если это ответ
       media_type TEXT,     -- Тип медиа (photo, video, document и т.д.)
       -- Другие важные метаданные
       additional_data JSONB,  -- Только для дополнительных данных, не используемых в поиске
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
       PRIMARY KEY (id, dialog_id)
   );
   ```

2. **Миграция данных:**
   ```python
   async def migrate_messages_to_optimized_structure(self):
       """Миграция данных в оптимизированную структуру"""
       async with self.connection_pool.acquire() as connection:
           # Проверяем, существует ли новая таблица
           table_exists = await connection.fetchval('''
               SELECT EXISTS(
                   SELECT 1 FROM information_schema.tables 
                   WHERE table_name = 'messages_optimized'
               )
           ''')
           
           if not table_exists:
               # Создаем новую таблицу
               await connection.execute('''
                   CREATE TABLE messages_optimized (
                       id BIGINT NOT NULL,
                       dialog_id BIGINT NOT NULL,
                       sender_id BIGINT,
                       sender_name TEXT,
                       text TEXT,
                       date TIMESTAMP NOT NULL,
                       account_id TEXT NOT NULL,
                       message_thread_id BIGINT,
                       has_reply BOOLEAN,
                       reply_to_id BIGINT,
                       media_type TEXT,
                       additional_data JSONB,
                       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                       updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                       PRIMARY KEY (id, dialog_id)
                   )
               ''')
               
               # Миграция данных
               await connection.execute('''
                   INSERT INTO messages_optimized (
                       id, dialog_id, sender_id, sender_name, text, date, account_id, 
                       message_thread_id, has_reply, reply_to_id, media_type, 
                       additional_data, created_at, updated_at
                   )
                   SELECT 
                       id, dialog_id, sender_id, sender_name, text, date, account_id,
                       message_thread_id,
                       (data->>'has_reply')::boolean,
                       (data->>'reply_to_id')::bigint,
                       data->>'media_type',
                       data, created_at, updated_at
                   FROM messages
               ''')
               
               # Создаем индексы
               await connection.execute('''
                   CREATE INDEX idx_messages_opt_sender ON messages_optimized (sender_name);
                   CREATE INDEX idx_messages_opt_dialog_date ON messages_optimized (dialog_id, date DESC);
                   CREATE INDEX idx_messages_opt_thread ON messages_optimized (message_thread_id);
                   CREATE INDEX idx_messages_opt_account ON messages_optimized (account_id);
                   CREATE INDEX idx_messages_opt_has_reply ON messages_optimized (has_reply);
                   CREATE INDEX idx_messages_opt_media_type ON messages_optimized (media_type);
               ''')
   ```

3. **Селективное использование полей:**
   ```python
   async def get_message_fields(self, message_id: int, dialog_id: int, fields: List[str]) -> Dict[str, Any]:
       """Получение выбранных полей сообщения"""
       try:
           async with self.connection_pool.acquire() as connection:
               # Строим запрос только для запрошенных полей
               fields_str = ', '.join(fields)
               query = f'''
                   SELECT {fields_str} FROM messages_optimized 
                   WHERE id = $1 AND dialog_id = $2
               '''
               
               result = await connection.fetchrow(query, message_id, dialog_id)
               if result:
                   return dict(result)
               return {}
       except Exception as e:
           self.log(f"Ошибка при получении полей сообщения: {e}")
           return {}
   ```

## 6. Кеширование поисковых запросов

**Проблема:** Отсутствие механизма для кеширования результатов поисковых запросов, что приводит к повторному выполнению одинаковых тяжелых запросов.

**Решение:**

1. **Создание таблицы для кеширования поисковых запросов:**
   ```sql
   CREATE TABLE search_cache (
       id SERIAL PRIMARY KEY,
       account_id TEXT NOT NULL,
       search_query TEXT NOT NULL,
       dialog_ids TEXT NOT NULL,  -- Сериализованный список JSON
       params JSONB NOT NULL,     -- Параметры поиска
       results JSONB NOT NULL,    -- Результаты поиска
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       expires_at TIMESTAMP NOT NULL  -- Время истечения кеша
   );
   
   -- Индекс для быстрого поиска кешированных запросов
   CREATE INDEX idx_search_cache_query ON search_cache (account_id, search_query, dialog_ids);
   
   -- Индекс для удаления устаревших записей
   CREATE INDEX idx_search_cache_expires ON search_cache (expires_at);
   ```

2. **Функции для работы с кешем поисковых запросов:**
   ```python
   async def cache_search_results(self, account_id: str, search_query: str, dialog_ids: List[int], 
                               params: Dict[str, Any], results: List[Dict[str, Any]], 
                               cache_ttl: int = 3600) -> bool:
       """Кеширование результатов поиска"""
       try:
           async with self.connection_pool.acquire() as connection:
               # Сериализация списка ID диалогов и параметров поиска
               dialog_ids_json = json.dumps(dialog_ids)
               params_json = json.dumps(params)
               results_json = json.dumps(results)
               
               # Время истечения кеша
               expires_at = datetime.datetime.now() + datetime.timedelta(seconds=cache_ttl)
               
               # Сохранение в кеш
               await connection.execute('''
                   INSERT INTO search_cache (account_id, search_query, dialog_ids, params, results, expires_at)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   ON CONFLICT (account_id, search_query, dialog_ids)
                   DO UPDATE SET
                       params = $4,
                       results = $5,
                       expires_at = $6,
                       created_at = NOW()
               ''', account_id, search_query, dialog_ids_json, params_json, results_json, expires_at)
               
               return True
       except Exception as e:
           self.log(f"Ошибка при кешировании результатов поиска: {e}")
           return False
   
   async def get_cached_search_results(self, account_id: str, search_query: str, 
                                     dialog_ids: List[int], params: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
       """Получение кешированных результатов поиска"""
       try:
           async with self.connection_pool.acquire() as connection:
               # Сериализация списка ID диалогов
               dialog_ids_json = json.dumps(dialog_ids)
               
               # Получение кешированных результатов
               row = await connection.fetchrow('''
                   SELECT results, expires_at FROM search_cache
                   WHERE account_id = $1 AND search_query = $2 AND dialog_ids = $3
                   AND expires_at > NOW()
               ''', account_id, search_query, dialog_ids_json)
               
               if row:
                   # Проверка срока истечения
                   if row['expires_at'] > datetime.datetime.now():
                       return json.loads(row['results'])
               
               return None
       except Exception as e:
           self.log(f"Ошибка при получении кешированных результатов поиска: {e}")
           return None
   
   async def cleanup_expired_search_cache(self):
       """Очистка устаревших записей кеша поиска"""
       try:
           async with self.connection_pool.acquire() as connection:
               result = await connection.execute('''
                   DELETE FROM search_cache
                   WHERE expires_at < NOW()
               ''')
               deleted_count = int(result.split(" ")[1]) if result else 0
               self.log(f"Удалено {deleted_count} устаревших записей кеша поиска")
               return deleted_count
       except Exception as e:
           self.log(f"Ошибка при очистке устаревших записей кеша поиска: {e}")
           return 0
   ```

## 7. Поддержка поиска по нескольким чатам

**Проблема:** Текущая реализация не поддерживает эффективный поиск по нескольким чатам одновременно.

**Решение:**

1. **Функция для поиска по нескольким чатам:**
   ```python
   async def search_messages_multi_chat(self, dialog_ids: List[int], search_params: Dict[str, Any], 
                                       account_id: str, limit: int = 100) -> Dict[int, List[Dict[str, Any]]]:
       """Поиск сообщений по нескольким чатам"""
       try:
           # Проверяем кеш поиска
           cache_key = f"{account_id}_{json.dumps(search_params)}_{json.dumps(dialog_ids)}"
           cached_results = await self.get_cached_search_results(
               account_id, search_params.get('text', ''), dialog_ids, search_params)
           
           if cached_results:
               self.log(f"Найдены кешированные результаты поиска для ключа {cache_key}")
               return cached_results
           
           # Если кеша нет, выполняем поиск
           async with self.connection_pool.acquire() as connection:
               # Формируем базовый SQL запрос
               base_query = '''
                   SELECT dialog_id, data FROM messages_optimized 
                   WHERE account_id = $1 AND dialog_id = ANY($2)
               '''
               
               conditions = []
               params = [account_id, dialog_ids]
               param_index = 3
               
               # Добавляем условия поиска
               if 'sender' in search_params and search_params['sender']:
                   conditions.append(f"sender_name ILIKE ${param_index}")
                   params.append(f"%{search_params['sender']}%")
                   param_index += 1
               
               if 'date' in search_params and search_params['date']:
                   # Преобразуем дату
                   date = standardize_date(search_params['date'])
                   next_day = date + datetime.timedelta(days=1)
                   conditions.append(f"date BETWEEN ${param_index} AND ${param_index+1}")
                   params.append(date)
                   params.append(next_day)
                   param_index += 2
               
               if 'text' in search_params and search_params['text']:
                   # Полнотекстовый поиск
                   conditions.append(f"ts_text @@ plainto_tsquery('russian', ${param_index})")
                   params.append(search_params['text'])
                   param_index += 1
               
               if 'reply_status' in search_params:
                   if search_params['reply_status'] == 'replied':
                       conditions.append("has_reply = TRUE")
                   elif search_params['reply_status'] == 'not_replied':
                       conditions.append("has_reply = FALSE")
               
               # Добавляем условия в запрос
               if conditions:
                   base_query += " AND " + " AND ".join(conditions)
               
               # Добавляем сортировку и лимит
               base_query += " ORDER BY date DESC LIMIT $" + str(param_index)
               params.append(limit)
               
               # Выполняем запрос
               rows = await connection.fetch(base_query, *params)
               
               # Группируем результаты по диалогам
               results = {}
               for row in rows:
                   dialog_id = row['dialog_id']
                   message_data = json.loads(row['data'])
                   
                   if dialog_id not in results:
                       results[dialog_id] = []
                   
                   results[dialog_id].append(message_data)
               
               # Кешируем результаты поиска
               await self.cache_search_results(
                   account_id, search_params.get('text', ''), dialog_ids, search_params, results)
               
               return results
       except Exception as e:
           self.log(f"Ошибка при поиске сообщений по нескольким чатам: {e}")
           import traceback
           self.log(traceback.format_exc())
           return {}
   ```

2. **Синхронизация метаданных для нескольких чатов:**
   ```python
   async def sync_dialog_metadata(self, dialog_ids: List[int], account_id: str):
       """Синхронизация метаданных диалогов"""
       try:
           async with self.connection_pool.acquire() as connection:
               # Обновление статистики по диалогам
               for dialog_id in dialog_ids:
                   # Подсчёт количества сообщений
                   msg_count = await connection.fetchval('''
                       SELECT COUNT(*) FROM messages_optimized 
                       WHERE dialog_id = $1 AND account_id = $2
                   ''', dialog_id, account_id)
                   
                   # Подсчёт количества отвеченных сообщений
                   replied_count = await connection.fetchval('''
                       SELECT COUNT(*) FROM messages_optimized 
                       WHERE dialog_id = $1 AND account_id = $2 AND has_reply = TRUE
                   ''', dialog_id, account_id)
                   
                   # Обновление метаданных диалога
                   await connection.execute('''
                       UPDATE dialogs 
                       SET data = jsonb_set(
                           data::jsonb, 
                           '{message_stats}', 
                           $3::jsonb, 
                           true
                       )
                       WHERE id = $1 AND account_id = $2
                   ''', dialog_id, account_id, json.dumps({
                       'total_messages': msg_count,
                       'replied_messages': replied_count,
                       'last_updated': datetime.datetime.now().isoformat()
                   }))
           
           return True
       except Exception as e:
           self.log(f"Ошибка при синхронизации метаданных диалогов: {e}")
           return False
   ```

## 8. Поддержка пагинации для больших наборов данных

**Проблема:** Отсутствие пагинации при работе с большими наборами данных.

**Решение:**

1. **Функция для пагинации результатов поиска:**
   ```python
   async def search_with_pagination(self, dialog_ids: List[int], search_params: Dict[str, Any], 
                                 account_id: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
       """Поиск сообщений с пагинацией"""
       try:
           # Базовый SQL запрос для поиска
           base_query, params = self._build_search_query(
               dialog_ids, search_params, account_id)
           
           # Запрос для подсчёта общего количества результатов
           count_query = f"SELECT COUNT(*) FROM ({base_query}) AS count_query"
           
           # Запрос с пагинацией
           paginated_query = f"{base_query} LIMIT {page_size} OFFSET {(page - 1) * page_size}"
           
           async with self.connection_pool.acquire() as connection:
               # Получаем общее количество результатов
               total_count = await connection.fetchval(count_query, *params)
               
               # Получаем результаты для текущей страницы
               rows = await connection.fetch(paginated_query, *params)
               
               # Преобразуем результаты
               results = [json.loads(row['data']) for row in rows]
               
               # Информация о пагинации
               total_pages = (total_count + page_size - 1) // page_size
               has_next = page < total_pages
               has_prev = page > 1
               
               return {
                   'results': results,
                   'pagination': {
                       'page': page,
                       'page_size': page_size,
                       'total_count': total_count,
                       'total_pages': total_pages,
                       'has_next': has_next,
                       'has_prev': has_prev
                   }
               }
       except Exception as e:
           self.log(f"Ошибка при поиске с пагинацией: {e}")
           return {'results': [], 'pagination': {'page': 1, 'total_count': 0, 'total_pages': 0}}
   
   def _build_search_query(self, dialog_ids: List[int], search_params: Dict[str, Any], 
                         account_id: str) -> Tuple[str, List[Any]]:
       """Построение SQL запроса и параметров для поиска"""
       # Базовый запрос
       base_query = '''
           SELECT dialog_id, data FROM messages_optimized 
           WHERE account_id = $1 AND dialog_id = ANY($2)
       '''
       
       conditions = []
       params = [account_id, dialog_ids]
       param_index = 3
       
       # Добавляем условия поиска (аналогично функции search_messages_multi_chat)
       if 'sender' in search_params and search_params['sender']:
           conditions.append(f"sender_name ILIKE ${param_index}")
           params.append(f"%{search_params['sender']}%")
           param_index += 1
       
       # Продолжение реализации условий...
       
       # Добавляем условия в запрос
       if conditions:
           base_query += " AND " + " AND ".join(conditions)
       
       # Добавляем сортировку
       base_query += " ORDER BY date DESC"
       
       return base_query, params
   ```

2. **Функция для постепенной загрузки сообщений:**
   ```python
   async def load_messages_incremental(self, dialog_id: int, account_id: str, 
                                     last_message_id: Optional[int] = None, 
                                     count: int = 20) -> List[Dict[str, Any]]:
       """Постепенная загрузка сообщений (от более новых к более старым)"""
       try:
           async with self.connection_pool.acquire() as connection:
               query = '''
                   SELECT data FROM messages_optimized 
                   WHERE dialog_id = $1 AND account_id = $2
               '''
               
               params = [dialog_id, account_id]
               
               # Если указан ID последнего сообщения, загружаем старые сообщения
               if last_message_id is not None:
                   query += " AND id < $3"
                   params.append(last_message_id)
               
               # Сортировка и лимит
               query += " ORDER BY id DESC LIMIT $" + str(len(params) + 1)
               params.append(count)
               
               rows = await connection.fetch(query, *params)
               return [json.loads(row['data']) for row in rows]
       except Exception as e:
           self.log(f"Ошибка при постепенной загрузке сообщений: {e}")
           return []
   ```

## Стратегия внедрения

Для минимизации рисков и обеспечения обратной совместимости, предлагается внедрять изменения в следующей последовательности:

1. **Этап 1: Оптимизация существующих структур**
   * Создание индексов для часто используемых полей поиска
   * Оптимизация транзакций для вставки большого количества данных
   * Реализация адаптивной подгрузки данных

2. **Этап 2: Расширение функциональности**
   * Добавление полнотекстового поиска
   * Оптимизация работы с датами
   * Реализация пагинации

3. **Этап 3: Реструктуризация данных**
   * Создание новой оптимизированной структуры таблиц
   * Миграция данных
   * Переключение на новую структуру с сохранением обратной совместимости

4. **Этап 4: Усовершенствованное кеширование**
   * Реализация кеширования поисковых запросов
   * Поддержка поиска по нескольким чатам

## Тестирование

После реализации каждого этапа необходимо провести тестирование:

1. **Тесты производительности**
   * Измерение времени выполнения запросов до и после оптимизации
   * Определение максимальной нагрузки на систему

2. **Тесты корректности**
   * Проверка, что результаты поиска совпадают с ожидаемыми
   * Тестирование различных комбинаций параметров поиска

3. **Нагрузочные тесты**
   * Тестирование при большом количестве одновременных запросов
   * Проверка стабильности при работе с большими объемами данных