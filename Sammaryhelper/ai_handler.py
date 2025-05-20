import openai
from typing import List, Dict, Any

class AIChatManager:
    def __init__(self, settings):
        self.settings = settings
        self.openai_client = None

    async def get_response(self, user_query, context=""):
        """Получение ответа от модели ИИ на запрос пользователя
        
        Args:
            user_query: Запрос пользователя
            context: Контекст сообщений для анализа
        
        Returns:
            str: Ответ от модели ИИ
        """
        try:
            # Инициализируем клиент OpenAI при необходимости
            if self.openai_client is None:
                self.openai_client = openai.AsyncOpenAI(api_key=self.settings.get('openai_api_key'))
            
            # Получаем выбранную модель и системный промпт из настроек
            model = self.settings.get('openai_model', 'gpt-3.5-turbo')
            # Проверка значения модели из настроек
            if not isinstance(model, str) or not model:
                print("Предупреждение: Недействительное значение 'openai_model' в настройках. Используется значение по умолчанию 'gpt-3.5-turbo'.")
                model = 'gpt-3.5-turbo'
            
            # Проверка, является ли значение модели строкой, содержащей JSON-словарь
            if isinstance(model, str):
                try:
                    import json
                    model_data = json.loads(model)
                    if isinstance(model_data, dict) and 'id' in model_data:
                        print(f"Обнаружен JSON-словарь в значении 'openai_model'. Извлечение ID модели: {model_data['id']}")
                        model = model_data['id']
                except (json.JSONDecodeError, ValueError):
                    # Если строка не является валидным JSON, оставляем значение как есть
                    pass
                    
            # Проверка, не является ли модель алиасом
            model_aliases = {
                'gpt4-latest': 'gpt-4o',  # Используем gpt-4o вместо конкретной версии
                'gpt3-latest': 'gpt-3.5-turbo'
            }
            
            if model in model_aliases:
                print(f"Обнаружен алиас модели '{model}'. Используется модель: {model_aliases[model]}")
                model = model_aliases[model]

            # Получаем список доступных моделей
            available_models = await self.get_available_models()
            available_model_ids = [m['id'] for m in available_models]
            
            # Список моделей, которые могут не возвращаться API, но фактически доступны
            known_available_models = [
                "gpt-4.1-nano-2025-04-14",
                # Здесь можно добавить другие модели, которые известны как доступные
            ]
            
            # Определяем, является ли выбранная модель чат-моделью
            is_chat_model = not ("realtime-preview" in model or any(prefix in model for prefix in ["davinci", "curie", "babbage", "ada"]))
            
            # Проверяем, доступна ли выбранная модель
            if model not in available_model_ids and model not in known_available_models:
                print(f"Предупреждение: Выбранная модель '{model}' недоступна.")
                if available_model_ids:
                    # Выбираем запасную модель того же типа, исключая специализированные модели
                    fallback_models = []
                    for m in available_models:
                        # Проверяем, является ли модель чат-моделью
                        model_is_chat = not ("realtime-preview" in m['id'] or any(prefix in m['id'] for prefix in ["davinci", "curie", "babbage", "ada"]))
                        
                        # Исключаем модели, требующие аудио-контент или другие специализированные модели
                        is_specialized = (
                            "audio" in m['id'] or
                            "vision" in m['id'] or
                            "whisper" in m['id'] or
                            "dall-e" in m['id']
                        )
                        
                        # Проверяем возможности модели, если они указаны
                        has_special_requirements = False
                        if 'capabilities' in m:
                            capabilities = m.get('capabilities', {})
                            # Проверяем, требует ли модель специальных возможностей
                            if capabilities.get('requires_audio') or capabilities.get('requires_vision'):
                                has_special_requirements = True
                        
                        # Добавляем модель в список запасных, если она подходит
                        if model_is_chat == is_chat_model and not is_specialized and not has_special_requirements:
                            fallback_models.append(m['id'])
                    
                    if fallback_models:
                        # Сортируем модели, чтобы предпочитать стандартные модели
                        # Предпочитаем модели без даты в названии или с более новой датой
                        sorted_models = sorted(fallback_models,
                                              key=lambda x: (
                                                  # Предпочитаем модели без даты
                                                  "-20" in x,
                                                  # Затем сортируем по имени (чтобы gpt-4 был перед gpt-3.5)
                                                  -len(x.split('-')[0]),
                                                  # Затем по дате (если есть)
                                                  x
                                              ))
                        
                        fallback_model = sorted_models[0]
                        print(f"Используется запасная модель того же типа: '{fallback_model}'.")
                    else:
                        # Если нет подходящих моделей того же типа, используем базовую модель
                        default_models = ["gpt-4o", "gpt-4", "gpt-3.5-turbo"]
                        fallback_model = next((m for m in default_models if m in available_model_ids), available_model_ids[0])
                        print(f"Нет доступных моделей того же типа. Используется модель: '{fallback_model}'.")
                    
                    model = fallback_model
                else:
                    print("Ошибка: Нет доступных моделей для использования.")
                    # Если нет доступных моделей, оставляем текущее значение model.
                    # API вызов, скорее всего, завершится ошибкой, которая будет обработана в блоке except.
                    pass

            system_prompt = self.settings.get('system_prompt', 'Ты - помощник, который помагает анализировать чаты и сообщения')

            # Определяем, является ли модель чат-моделью
            is_chat_model = True
            
            # Проверяем, содержит ли ID модели ключевые слова, указывающие на не-чат модель
            # "realtime-preview" указывает на модели, которые используют completions API вместо chat.completions
            if "realtime-preview" in model or any(prefix in model for prefix in ["davinci", "curie", "babbage", "ada"]):
                is_chat_model = False
                print(f"Модель '{model}' определена как не-чат модель. Используется эндпоинт completions.")
            
            # Формируем запрос к API в зависимости от типа модели
            if is_chat_model:
                # Для чат-моделей используем chat.completions.create
                response = await self.openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Контекст сообщений:\n{context}\n\nЗапрос: {user_query}"}
                    ]
                )
            else:
                # Для не-чат моделей используем completions.create
                prompt = f"{system_prompt}\n\nКонтекст сообщений:\n{context}\n\nЗапрос: {user_query}"
                response = await self.openai_client.completions.create(
                    model=model,
                    prompt=prompt,
                    max_tokens=1000
                )
            
            # Извлекаем ответ в зависимости от типа модели
            if is_chat_model:
                ai_response = response.choices[0].message.content
            else:
                ai_response = response.choices[0].text.strip()
            
            return ai_response
            
        except Exception as e:
            print(f"Ошибка при получении ответа от ИИ: {e}")
            import traceback
            print(traceback.format_exc())
            return f"Произошла ошибка при обработке запроса: {str(e)}"

    async def generate_summary(self, messages: List[str], openai_client) -> str:
        """Генерация саммари"""
        if not messages:
            return "Нет сообщений для анализа"

        def estimate_tokens(text: str) -> int:
            return len(text) // 4

        MAX_TOKENS = 14000
        current_chunk = []
        chunks = []
        current_tokens = 0

        for message in messages:
            message_tokens = estimate_tokens(message)
            if current_tokens + message_tokens > MAX_TOKENS:
                chunks.append(current_chunk)
                current_chunk = [message]
                current_tokens = message_tokens
            else:
                current_chunk.append(message)
                current_tokens += message_tokens

        if current_chunk:
            chunks.append(current_chunk)

        summaries = []
        user_prompt = self.settings['user_prompt']
        model = self.settings['openai_model']
        system_prompt = self.settings['system_prompt']
        
        # Определяем, является ли модель чат-моделью
        is_chat_model = True
        # "realtime-preview" и другие префиксы указывают на не-чат модели
        if "realtime-preview" in model or any(prefix in model for prefix in ["davinci", "curie", "babbage", "ada"]):
            is_chat_model = False
            print(f"Модель '{model}' определена как не-чат модель. Используется эндпоинт completions.")

        for i, chunk in enumerate(chunks):
            chunk_prompt = user_prompt + "\n\n"
            chunk_prompt += "\n".join(chunk)
            chunk_prompt += "\n\nКраткое содержание:"

            try:
                if is_chat_model:
                    # Для чат-моделей используем chat.completions.create
                    response = await openai_client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": chunk_prompt}
                        ]
                    )
                    summaries.append(response.choices[0].message.content)
                else:
                    # Для не-чат моделей используем completions.create
                    full_prompt = f"{system_prompt}\n\n{chunk_prompt}"
                    response = await openai_client.completions.create(
                        model=model,
                        prompt=full_prompt,
                        max_tokens=1000
                    )
                    summaries.append(response.choices[0].text.strip())
            except Exception as e:
                summaries.append(f"Ошибка при генерации саммари части {i+1}: {str(e)}")

        if len(summaries) > 1:
            try:
                final_prompt = "Объедини следующие саммари частей переписки в одно краткое и связное содержание:\n\n"
                
                for i, summary in enumerate(summaries):
                    final_prompt += f"Часть {i+1}:\n{summary}\n\n"
                
                final_prompt += "Общее краткое содержание:"

                if is_chat_model:
                    # Для чат-моделей используем chat.completions.create
                    response = await openai_client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": final_prompt}
                        ]
                    )
                    return response.choices[0].message.content
                else:
                    # Для не-чат моделей используем completions.create
                    full_prompt = f"{system_prompt}\n\n{final_prompt}"
                    response = await openai_client.completions.create(
                        model=model,
                        prompt=full_prompt,
                        max_tokens=1000
                    )
                    return response.choices[0].text.strip()
            except Exception as e:
                return f"Ошибка при генерации финального саммари: {str(e)}"
        else:
            return summaries[0]

    async def analyze_participants(self, participants: List[Dict[str, Any]], openai_client) -> str:
        """Анализ участников чата"""
        try:
            participants_info = "\n".join([f"{p['username']} ({p['first_name']} {p['last_name']})" for p in participants])
            prompt = f"""Проанализируй участников чата и выдели ключевых участников:

{participants_info}

Ключевые участники:"""
            
            model = self.settings['openai_model']
            system_prompt = self.settings['system_prompt']
            
            # Определяем, является ли модель чат-моделью
            is_chat_model = True
            # Проверка на не-чат модели по идентификаторам
            if "realtime-preview" in model or any(prefix in model for prefix in ["davinci", "curie", "babbage", "ada"]):
                is_chat_model = False
                print(f"Модель '{model}' определена как не-чат модель. Используется эндпоинт completions.")
            
            if is_chat_model:
                # Для чат-моделей используем chat.completions.create
                response = await openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
            else:
                # Для не-чат моделей используем completions.create
                full_prompt = f"{system_prompt}\n\n{prompt}"
                response = await openai_client.completions.create(
                    model=model,
                    prompt=full_prompt,
                    max_tokens=1000
                )
                return response.choices[0].text.strip()
        except Exception as e:
            return f"Ошибка при анализе участников чата: {str(e)}"

    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Получение списка доступных моделей OpenAI с их свойствами
        
        Returns:
            List[Dict[str, Any]]: Список словарей с информацией о моделях,
            где каждый словарь содержит:
            - id: идентификатор модели
            - created: дата создания
            - owned_by: владелец модели
            - capabilities: возможности модели
        """
        try:
            # Инициализируем клиент OpenAI при необходимости
            if self.openai_client is None:
                self.openai_client = openai.AsyncOpenAI(api_key=self.settings.get('openai_api_key'))
            
            # Получаем список моделей
            models = await self.openai_client.models.list()
            
            # Форматируем результат
            return [
                {
                    "id": model.id,
                    "created": model.created,
                    "owned_by": model.owned_by,
                    "capabilities": {
                        "chat": "gpt" in model.id and "realtime-preview" not in model.id,
                        "completion": "davinci" in model.id or "curie" in model.id or "babbage" in model.id or "ada" in model.id or "realtime-preview" in model.id,
                        "embedding": "embedding" in model.id,
                        "requires_audio": "audio" in model.id or "whisper" in model.id,
                        "requires_vision": "vision" in model.id or "dall-e" in model.id
                    }
                }
                for model in models.data
            ]
            
        except Exception as e:
            print(f"Ошибка при получении списка моделей: {e}")
            import traceback
            print(traceback.format_exc())
            return []

    async def select_model(self) -> str:
        """Выбор модели из списка доступных
        
        Returns:
            str: Идентификатор выбранной модели
        """
        try:
            # Получаем список доступных моделей
            models = await self.get_available_models()
            if not models:
                print("Нет доступных моделей")
                return ""
            
            # Выводим список моделей с нумерацией
            print("\nДоступные модели:")
            for i, model in enumerate(models, 1):
                print(f"{i}. {model['id']}")
                print(f"   Создана: {model['created']}")
                print(f"   Владелец: {model['owned_by']}")
                print(f"   Возможности: {'Чат' if model['capabilities']['chat'] else ''} "
                      f"{'Завершение текста' if model['capabilities']['completion'] else ''} "
                      f"{'Векторизация' if model['capabilities']['embedding'] else ''}")
                print()
            
            # Запрашиваем выбор пользователя
            while True:
                try:
                    choice = input("Выберите номер модели (или 0 для отмены): ")
                    if choice == "0":
                        return ""
                    
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(models):
                        selected_model = models[choice_idx]['id']
                        self.settings['openai_model'] = selected_model
                        print(f"Выбрана модель: {selected_model}")
                        return selected_model
                    else:
                        print("Неверный номер. Попробуйте снова.")
                except ValueError:
                    print("Пожалуйста, введите число.")
                
        except Exception as e:
            print(f"Ошибка при выборе модели: {e}")
            import traceback
            print(traceback.format_exc())
            return ""