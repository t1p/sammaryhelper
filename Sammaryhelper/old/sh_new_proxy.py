import sys
import os
import importlib.util
from telethon import TelegramClient
from telethon.tl.types import Channel, User
from datetime import datetime, timedelta
import openai
from typing import List
import pytz

def load_config(config_name):
    config_path = f"configs/{config_name}.py"
    try:
        if not os.path.exists(config_path):
            print(f"Файл конфига не найден: {config_path}")
            print(f"Текущая директория: {os.getcwd()}")
            sys.exit(1)
            
        spec = importlib.util.spec_from_file_location("config", config_path)
        if spec is None:
            print(f"Не удалось создать spec для: {config_path}")
            sys.exit(1)
            
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        return config
    except Exception as e:
        print(f"Ошибка загрузки конфига: {str(e)}")
        print(f"Тип ошибки: {type(e).__name__}")
        sys.exit(1)

async def get_chat_messages(client: TelegramClient, chat_link: str, limit_hours: int = 24) -> List[str]:
    """Получение сообщений из чата за последние limit_hours часов"""
    messages = []
    current_time = datetime.now(pytz.UTC)
    time_limit = current_time - timedelta(hours=limit_hours)
    
    print(f"Текущее время UTC: {current_time}")
    print(f"Собираем сообщения с: {time_limit}")
    
    try:
        entity = await client.get_entity(chat_link)
        print(f"Начинаем сбор сообщений из: {entity.title}")
        
        async for message in client.iter_messages(entity, limit=None):
            if message.date < time_limit:
                print(f"Достигнут предел по времени ({message.date})")
                break
                
            if message.text:
                formatted_date = message.date.strftime("%Y-%m-%d %H:%M:%S UTC")
                messages.append(f"{formatted_date}: {message.text}")
                print(f"[+] Собрано сообщение от {formatted_date}")
    except Exception as e:
        print(f"Ошибка при получении сообщений: {e}")
        print(f"Тип ошибки: {type(e)}")
        return []
    
    print(f"\nВсего собрано сообщений: {len(messages)}")
    return messages

async def generate_summary(messages: List[str], openai_client) -> str:
    """Генерация саммари через OpenAI API"""
    if not messages:
        return "Нет сообщений для анализа"
    
    prompt = f"""Пожалуйста, создай краткое содержание следующей переписки, выделив основные темы и ключевые моменты обсуждения:

{'\n'.join(messages)}

Краткое содержание:"""

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты - помощник, который создает краткие и информативные саммари дискуссий."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка при генерации саммари: {str(e)}"

async def list_dialogs(client: TelegramClient):
    """Получение списка доступных диалогов"""
    print("\nДоступные диалоги:")
    print("-" * 50)
    dialogs = []
    async for dialog in client.iter_dialogs():
        dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
        dialogs.append({
            'id': dialog.id,
            'name': dialog.name,
            'type': dialog_type,
            'entity': dialog.entity
        })
        print(f"{len(dialogs)-1}. [{dialog_type}] {dialog.name}")
    print("-" * 50)
    return dialogs

async def select_target_chat(client: TelegramClient, target_identifier: str) -> object:
    """Выбор целевого чата для отправки саммари"""
    try:
        # Если передан числовой индекс
        if target_identifier.isdigit():
            dialogs = await list_dialogs(client)
            index = int(target_identifier)
            if 0 <= index < len(dialogs):
                return dialogs[index]['entity']
            else:
                print("Неверный индекс диалога")
                return None
                
        # Если передан username или ссылка
        else:
            entity = await client.get_entity(target_identifier)
            return entity
            
    except Exception as e:
        print(f"Ошибка при выборе целевого чата: {e}")
        print("Выберите чат из списка, указав его номер:")
        dialogs = await list_dialogs(client)
        
        while True:
            try:
                choice = input("Введите номер чата: ")
                index = int(choice)
                if 0 <= index < len(dialogs):
                    return dialogs[index]['entity']
                else:
                    print("Неверный номер. Попробуйте еще раз.")
            except ValueError:
                print("Пожалуйста, введите число.")
            except Exception as e:
                print(f"Ошибка: {e}")
                return None

async def main(config_name: str, source_chat: str, target_chat: str, hours: int = 24):
    config = load_config(config_name)
    
    openai_client = openai.AsyncOpenAI(api_key=config.openai_api_key)
    proxy_settings = (config.proxy_type, config.proxy_host, config.proxy_port) if hasattr(config, 'proxy_type') else None
    
    async with TelegramClient('anon', config.api_id, config.api_hash, proxy=proxy_settings) as client:
        # Получаем сообщения из исходного чата
        messages = await get_chat_messages(client, source_chat, hours)
        
        if not messages:
            print("Нет сообщений для обработки")
            return
        
        # Выбираем целевой чат
        target_entity = await select_target_chat(client, target_chat)
        if not target_entity:
            print("Не удалось определить целевой чат")
            return
            
        # Генерируем и отправляем саммари
        summary = await generate_summary(messages, openai_client)
        await client.send_message(target_entity, f"📝 Саммари чата {source_chat} за последние {hours} часов:\n\n{summary}")
        print("Саммари успешно отправлено!")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Использование:")
        print("1. По username/ссылке: python sh_new_proxy.py <имя_конфига> <источник> @username [часы]")
        print("2. По номеру из списка: python sh_new_proxy.py <имя_конфига> <источник> номер [часы]")
        print("Примеры:")
        print("python sh_new_proxy.py config_1 https://t.me/channel_name @username 48")
        print("python sh_new_proxy.py config_1 https://t.me/channel_name 0 48")
        sys.exit(1)

    import asyncio
    config_name = sys.argv[1]
    source_chat = sys.argv[2]
    target_chat = sys.argv[3]
    hours = int(sys.argv[4]) if len(sys.argv) > 4 else 24
    
    asyncio.run(main(config_name, source_chat, target_chat, hours))
