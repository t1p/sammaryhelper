# Логирование работы с моделями

## Ключевые точки логирования

1. **API запросы:**
   - Уровень: INFO
   - Формат: "API Request: {endpoint} {params}"
   - Пример: "API Request: /models/list"

2. **Ответы API:**
   - Уровень: INFO
   - Формат: "API Response: {status} {data}"
   - Пример: "API Response: 200 [gpt-3.5-turbo, gpt-4]"

3. **Ошибки API:**
   - Уровень: ERROR
   - Формат: "API Error: {error}"
   - Пример: "API Error: Connection timeout"

4. **Выбор модели:**
   - Уровень: INFO
   - Формат: "Model selected: {model}"
   - Пример: "Model selected: gpt-4"

5. **Обновление списка моделей:**
   - Уровень: INFO
   - Формат: "Models updated: {count}"
   - Пример: "Models updated: 3"

## Конфигурация логгера

```python
import logging

logger = logging.getLogger('model_manager')
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Консольный вывод
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Файловый вывод
file_handler = logging.FileHandler('model_operations.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
```

## Интеграция с существующим кодом

1. В `ai_handler.py`:
```python
logger.info(f"API Request: models/list")
try:
    response = await client.models.list()
    logger.info(f"API Response: {len(response.data)} models")
except Exception as e:
    logger.error(f"API Error: {str(e)}")
    raise
```

2. В `gui.py`:
```python
def on_model_select(self, event):
    logger.info(f"Model selected: {self.model_var.get()}")
    self.settings['openai_model'] = self.model_var.get()
```

3. В `main.py`:
```python
if args.model:
    logger.info(f"CLI model change: {args.model}")
    ai_manager.settings['openai_model'] = args.model