import openai
from typing import List, Dict, Any

class AIChatManager:
    def __init__(self, settings):
        self.settings = settings
        self.openai_client = None
        self.conversation_history = []  # Добавляем хранение истории диалога

    async def get_response(self, user_query, context="", reset_context=False):
        """Получение ответа от модели ИИ на запрос пользователя
        
        Args:
            user_query: Запрос пользователя
            context: Контекст сообщений для анализа
            reset_context: Сбросить предыдущий контекст диалога
        
        Returns:
            str: Ответ от модели ИИ
        """
        try:
            # Сбрасываем историю, если требуется
            if reset_context:
                self.conversation_history = []
                
            # Инициализируем клиент OpenAI при необходимости
            if self.openai_client is None:
                self.openai_client = openai.AsyncOpenAI(api_key=self.settings.get('openai_api_key'))
            
            # Получаем выбранную модель и системный промпт из настроек
            model = self.settings.get('openai_model', 'gpt-3.5-turbo')
            system_prompt = self.settings.get('system_prompt', 'Ты - помощник, который помагает анализировать чаты и сообщения')
            
            # Создаем сообщение пользователя с контекстом
            user_message = f"Контекст сообщений:\n{context}\n\nЗапрос: {user_query}" if context else user_query
            
            # Добавляем новое сообщение пользователя в историю
            self.conversation_history.append({"role": "user", "content": user_message})
            
            # Формируем запрос к API с полной историей
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self.conversation_history)
            
            # Ограничиваем длину истории, если нужно (для предотвращения превышения лимита токенов)
            if len(messages) > 10:  # Например, оставляем только последние 10 сообщений
                # Системное сообщение + последние N сообщений из истории
                messages = [messages[0]] + messages[-10:]
            
            # Отправляем запрос к API
            response = await self.openai_client.chat.completions.create(
                model=model,
                messages=messages
            )
            
            # Извлекаем ответ
            ai_response = response.choices[0].message.content
            
            # Добавляем ответ ИИ в историю
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            
            return ai_response
            
        except Exception as e:
            print(f"Ошибка при получении ответа от ИИ: {e}")
            import traceback
            print(traceback.format_exc())
            return f"Произошла ошибка при обработке запроса: {str(e)}"

    def estimate_tokens(self, messages):
        """Оценка количества токенов в сообщениях"""
        # Простая оценка: 1 токен ≈ 4 символа
        total_chars = sum(len(m["content"]) for m in messages)
        estimated_tokens = total_chars // 4
        return estimated_tokens

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

        for i, chunk in enumerate(chunks):
            chunk_prompt = f"""{user_prompt}

{'\n'.join(chunk)}

Краткое содержание:"""

            try:
                response = await openai_client.chat.completions.create(
                    model=self.settings['openai_model'],
                    messages=[
                        {"role": "system", "content": self.settings['system_prompt']},
                        {"role": "user", "content": chunk_prompt}
                    ]
                )
                summaries.append(response.choices[0].message.content)
            except Exception as e:
                summaries.append(f"Ошибка при генерации саммари части {i+1}: {str(e)}")

        if len(summaries) > 1:
            try:
                final_prompt = f"""Объедини следующие саммари частей переписки в одно краткое и связное содержание:

{''.join(f"Часть {i+1}:\n{summary}\n\n" for i, summary in enumerate(summaries))}

Общее краткое содержание:"""

                response = await openai_client.chat.completions.create(
                    model=self.settings['openai_model'],
                    messages=[
                        {"role": "system", "content": self.settings['system_prompt']},
                        {"role": "user", "content": final_prompt}
                    ]
                )
                return response.choices[0].message.content
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
            
            response = await openai_client.chat.completions.create(
                model=self.settings['openai_model'],
                messages=[
                    {"role": "system", "content": self.settings['system_prompt']},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Ошибка при анализе участников чата: {str(e)}" 