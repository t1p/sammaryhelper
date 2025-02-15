import openai
from typing import List, Dict, Any

class AIChatManager:
    def __init__(self, settings):
        self.settings = settings

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