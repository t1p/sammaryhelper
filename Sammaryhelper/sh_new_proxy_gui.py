import sys
import os
import importlib.util
from telethon import TelegramClient
from telethon.tl.types import Channel, User
from datetime import datetime, timedelta
import openai
from typing import List
import pytz
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import asyncio
import threading
from functools import partial
import json

def load_config(config_name):
    """Загрузка конфигурационного файла"""
    config_path = f"configs/{config_name}.py"
    try:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфига не найден: {config_path}")
            
        spec = importlib.util.spec_from_file_location("config", config_path)
        if spec is None:
            raise ImportError(f"Не удалось создать spec для: {config_path}")
            
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        return config
    except Exception as e:
        raise Exception(f"Ошибка загрузки конфига: {str(e)}")

async def get_chat_messages(client: TelegramClient, chat_link: str, limit_hours: int = 24) -> List[str]:
    """Получение сообщений из чата за последние limit_hours часов"""
    messages = []
    current_time = datetime.now(pytz.UTC)
    time_limit = current_time - timedelta(hours=limit_hours)
    
    try:
        entity = await client.get_entity(chat_link)
        
        async for message in client.iter_messages(entity, limit=None):
            if message.date < time_limit:
                break
                
            if message.text:
                formatted_date = message.date.strftime("%Y-%m-%d %H:%M:%S UTC")
                messages.append(f"{formatted_date}: {message.text}")
    except Exception as e:
        raise Exception(f"Ошибка при получении сообщений: {e}")
    
    return messages

class TelegramSummarizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram Channel Summarizer")
        self.root.geometry("900x700")
        
        # Инициализация event loop
        self.loop = asyncio.new_event_loop()
        self.running = True
        
        # Создаем notebook для вкладок
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Основная вкладка
        self.main_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.main_frame, text="Основное")
        
        # Вкладка настроек
        self.settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.settings_frame, text="Настройки")
        
        # Инициализация настроек по умолчанию
        self.settings = {
            'openai_model': 'gpt-3.5-turbo',
            'system_prompt': 'Ты - помощник, который создает краткие и информативные саммари дискуссий.',
            'available_models': [
                'gpt-3.5-turbo',
                'gpt-4',
                'gpt-4-turbo-preview'
            ]
        }
        
        # Сначала создаем все элементы интерфейса
        self.setup_main_tab()
        self.setup_settings_tab()
        
        # Затем загружаем настройки
        self.load_settings()
        
        # Данные
        self.client = None
        self.dialogs = []
        
        # Добавляем обработчик изменения конфига
        self.config_combo.bind('<<ComboboxSelected>>', self.on_config_change)
    
    def setup_main_tab(self):
        """Настройка основной вкладки"""
        # Конфигурация
        ttk.Label(self.main_frame, text="Конфигурация:").grid(row=0, column=0, sticky=tk.W)
        self.config_var = tk.StringVar()
        self.config_combo = ttk.Combobox(self.main_frame, textvariable=self.config_var, state="readonly")
        configs = self.get_config_files()
        self.config_combo['values'] = configs
        if configs:  # Выбираем первый конфиг по умолчанию
            self.config_combo.set(configs[0])
        self.config_combo.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Источник
        ttk.Label(self.main_frame, text="Источник:").grid(row=1, column=0, sticky=tk.W)
        self.source_entry = ttk.Entry(self.main_frame)
        self.source_entry.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Временной интервал
        ttk.Label(self.main_frame, text="Часы:").grid(row=2, column=0, sticky=tk.W)
        self.hours_var = tk.StringVar(value="24")
        self.hours_entry = ttk.Entry(self.main_frame, textvariable=self.hours_var)
        self.hours_entry.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Пользовательский промпт
        ttk.Label(self.main_frame, text="Промпт:").grid(row=3, column=0, sticky=tk.W)
        self.user_prompt = scrolledtext.ScrolledText(self.main_frame, height=4)
        self.user_prompt.grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.user_prompt.insert('1.0', "Пожалуйста, создай краткое содержание переписки, выделив основные темы и ключевые моменты обсуждения:")
        
        # Фрейм для поиска и фильтров
        self.search_frame = ttk.Frame(self.main_frame)
        self.search_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Поле поиска
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_dialogs)
        ttk.Label(self.search_frame, text="🔍").pack(side=tk.LEFT, padx=2)
        self.search_entry = ttk.Entry(self.search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Фильтры типов чатов
        self.filter_frame = ttk.Frame(self.search_frame)
        self.filter_frame.pack(side=tk.LEFT, padx=5)
        
        self.show_channels = tk.BooleanVar(value=True)
        self.show_groups = tk.BooleanVar(value=True)
        self.show_private = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(self.filter_frame, text="Каналы", variable=self.show_channels, 
                       command=self.filter_dialogs).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(self.filter_frame, text="Группы", variable=self.show_groups,
                       command=self.filter_dialogs).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(self.filter_frame, text="Личные", variable=self.show_private,
                       command=self.filter_dialogs).pack(side=tk.LEFT, padx=2)
        
        # Сортировка
        self.sort_var = tk.StringVar(value="name")
        ttk.Label(self.filter_frame, text="Сортировка:").pack(side=tk.LEFT, padx=5)
        sort_combo = ttk.Combobox(self.filter_frame, textvariable=self.sort_var, 
                                 values=["имя", "тип", "папка"], state="readonly", width=10)
        sort_combo.pack(side=tk.LEFT, padx=2)
        sort_combo.bind('<<ComboboxSelected>>', self.filter_dialogs)
        
        # Список диалогов (теперь используем Treeview вместо Listbox)
        self.dialogs_frame = ttk.Frame(self.main_frame)
        self.dialogs_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Создаем Treeview
        self.dialogs_tree = ttk.Treeview(self.dialogs_frame, columns=('type', 'folder', 'id'),
                                        show='tree headings')
        self.dialogs_tree.heading('type', text='Тип')
        self.dialogs_tree.heading('folder', text='Папка')
        self.dialogs_tree.column('type', width=100)
        self.dialogs_tree.column('folder', width=100)
        # Скрываем колонку id
        self.dialogs_tree.column('id', width=0, stretch=False)
        
        # Добавляем скроллбар
        scrollbar = ttk.Scrollbar(self.dialogs_frame, orient=tk.VERTICAL, 
                                command=self.dialogs_tree.yview)
        self.dialogs_tree.configure(yscrollcommand=scrollbar.set)
        
        # Размещаем элементы
        self.dialogs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Кнопки
        self.buttons_frame = ttk.Frame(self.main_frame)
        self.buttons_frame.grid(row=6, column=0, columnspan=3, pady=10)
        
        self.load_dialogs_btn = ttk.Button(self.buttons_frame, text="Загрузить диалоги", 
                                         command=self.load_dialogs)
        self.load_dialogs_btn.pack(side=tk.LEFT, padx=5)
        
        self.start_btn = ttk.Button(self.buttons_frame, text="Создать саммари", 
                                  command=self.start_summarization)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        # Лог
        ttk.Label(self.main_frame, text="Лог:").grid(row=7, column=0, sticky=tk.W)
        self.log_text = tk.Text(self.main_frame, height=10, wrap=tk.WORD)
        self.log_text.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Прогресс
        self.progress = ttk.Progressbar(self.main_frame, mode='indeterminate')
        self.progress.grid(row=9, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
    
    def setup_settings_tab(self):
        """Настройка вкладки настроек"""
        # Выбор модели
        ttk.Label(self.settings_frame, text="Модель OpenAI:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar(value=self.settings['openai_model'])
        self.model_combo = ttk.Combobox(self.settings_frame, textvariable=self.model_var)
        self.model_combo['values'] = self.settings['available_models']
        self.model_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Системный промпт
        ttk.Label(self.settings_frame, text="Системный промпт:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.system_prompt = scrolledtext.ScrolledText(self.settings_frame, height=6)
        self.system_prompt.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.system_prompt.insert('1.0', self.settings['system_prompt'])
        
        # Кнопка сохранения
        self.save_btn = ttk.Button(self.settings_frame, text="Сохранить настройки", 
                                 command=self.save_settings)
        self.save_btn.grid(row=2, column=0, columnspan=2, pady=10)
    
    def load_settings(self):
        """Загрузка настроек из файла"""
        try:
            with open('summarizer_settings.json', 'r', encoding='utf-8') as f:
                saved_settings = json.load(f)
                self.settings.update(saved_settings)
                
                # Обновляем значения в интерфейсе
                self.model_var.set(self.settings['openai_model'])
                self.system_prompt.delete('1.0', tk.END)
                self.system_prompt.insert('1.0', self.settings['system_prompt'])
        except FileNotFoundError:
            # Создаем файл с настройками по умолчанию
            self.save_settings()
        except Exception as e:
            self.log(f"Ошибка при загрузке настроек: {e}")
    
    def save_settings(self):
        """Сохранение настроек в файл"""
        try:
            # Обновляем настройки из интерфейса
            if hasattr(self, 'model_var'):
                self.settings['openai_model'] = self.model_var.get()
            if hasattr(self, 'system_prompt'):
                self.settings['system_prompt'] = self.system_prompt.get('1.0', tk.END).strip()
            
            with open('summarizer_settings.json', 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            self.log("Настройки сохранены")
        except Exception as e:
            self.log(f"Ошибка при сохранении настроек: {e}")

    def get_config_files(self):
        """Получение списка конфигурационных файлов"""
        configs = []
        configs_dir = "configs"
        if not os.path.exists(configs_dir):
            os.makedirs(configs_dir)
            self.create_default_config()
            self.log("Создана папка configs с шаблоном конфига")
        
        for file in os.listdir(configs_dir):
            if file.endswith(".py") and not file.startswith("__"):
                configs.append(file[:-3])
        
        if not configs:
            self.create_default_config()
            configs = ["config_template"]
            self.log("Создан шаблон конфига config_template.py")
        
        return configs

    def create_default_config(self):
        """Создание шаблона конфигурационного файла"""
        config_template = """# Telegram API credentials
api_id = 123456  # Замените на ваш api_id
api_hash = 'your_api_hash_here'  # Замените на ваш api_hash

# Proxy settings
use_proxy = False  # Измените на True, если нужен прокси
proxy_settings = {
    'proxy_type': 'socks5',
    'proxy_host': '127.0.0.1',
    'proxy_port': 9150
}

# OpenAI API key
openai_api_key = 'your_openai_api_key_here'  # Замените на ваш ключ OpenAI
"""
        with open("configs/config_template.py", "w", encoding="utf-8") as f:
            f.write(config_template)

    def log(self, message):
        """Добавление сообщения в лог"""
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
        else:
            print(message)  # Fallback для случая, когда лог еще не создан
        
    async def init_client(self):
        """Инициализация клиента Telegram"""
        try:
            config_name = self.config_var.get()
            if not config_name:
                raise ValueError("Не выбран конфигурационный файл")
            
            # Закрываем предыдущую сессию, если она существует
            if hasattr(self, 'client') and self.client is not None:
                if self.client.is_connected():
                    await self.client.disconnect()
                self.client = None
                
            config = load_config(config_name)
            
            # Используем имя конфига как имя сессии
            session_name = f"sessions/{config_name}"
            
            # Создаем директорию для сессий, если её нет
            os.makedirs("sessions", exist_ok=True)
            
            # Проверяем настройки прокси
            proxy_settings = None
            if hasattr(config, 'use_proxy') and config.use_proxy and hasattr(config, 'proxy_settings'):
                proxy_settings = (
                    config.proxy_settings['proxy_type'],
                    config.proxy_settings['proxy_host'],
                    config.proxy_settings['proxy_port']
                )
            
            # Создаем новый клиент с сохранением сессии
            self.client = TelegramClient(session_name, config.api_id, config.api_hash, proxy=proxy_settings)
            
            # Подключаемся, но не запускаем новую сессию, если уже авторизованы
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                self.log(f"Требуется авторизация для конфига {config_name}. Проверьте консоль для ввода кода.")
                await self.client.start()
            else:
                self.log(f"Успешное подключение к сессии {config_name}")
                
            return True
        except Exception as e:
            self.log(f"Ошибка при инициализации клиента: {e}")
            if "Не выбран конфигурационный файл" in str(e):
                self.log("Пожалуйста, выберите конфигурационный файл из списка")
                self.log("Если список пуст, отредактируйте файл configs/config_template.py")
            return False

    def on_config_change(self, event):
        """Обработчик изменения конфига"""
        self.progress.start()
        
        async def reconnect():
            try:
                if hasattr(self, 'client') and self.client is not None:
                    if self.client.is_connected():
                        await self.client.disconnect()
                    self.client = None
                self.dialogs = []
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                self.log(f"Выбран конфиг: {self.config_var.get()}")
            finally:
                self.progress.stop()
            
        asyncio.run_coroutine_threadsafe(reconnect(), self.loop)

    def load_dialogs(self):
        """Загрузка списка диалогов"""
        self.progress.start()
        self.load_dialogs_btn.state(['disabled'])
        
        async def load():
            try:
                if not self.client or not self.client.is_connected():
                    if not await self.init_client():
                        return
                        
                self.dialogs = []
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                
                async for dialog in self.client.iter_dialogs():
                    dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
                    self.dialogs.append({
                        'id': dialog.id,
                        'name': dialog.name,
                        'type': dialog_type,
                        'entity': dialog.entity
                    })
                    self.dialogs_tree.insert('', 'end', text=dialog.name, values=(dialog_type, '', dialog.id))
                    
                self.log("Диалоги загружены")
            except Exception as e:
                self.log(f"Ошибка при загрузке диалогов: {e}")
            finally:
                self.progress.stop()
                self.load_dialogs_btn.state(['!disabled'])
                
        asyncio.run_coroutine_threadsafe(load(), self.loop)

    def cleanup(self):
        """Очистка ресурсов при закрытии приложения"""
        self.running = False
        
        async def cleanup_async():
            if hasattr(self, 'client') and self.client is not None:
                if self.client.is_connected():
                    await self.client.disconnect()
        
        try:
            # Выполняем асинхронную очистку
            future = asyncio.run_coroutine_threadsafe(cleanup_async(), self.loop)
            future.result(timeout=5)  # Ждем завершения не более 5 секунд
            
            # Останавливаем loop в отдельном потоке
            self.loop.call_soon_threadsafe(self.loop.stop)
            
        except Exception as e:
            print(f"Ошибка при очистке ресурсов: {e}")

    async def summarize(self):
        """Процесс создания саммари"""
        try:
            if not self.client or not self.client.is_connected():
                if not await self.init_client():
                    return

            # Получаем выбранный элемент
            selected_items = self.dialogs_tree.selection()
            if not selected_items:
                self.log("Не выбран целевой чат")
                return
                
            selected_item = selected_items[0]
            # Получаем id диалога из скрытой колонки
            dialog_id = self.dialogs_tree.item(selected_item)['values'][2]
            
            # Находим соответствующий диалог
            target_dialog = next((d for d in self.dialogs if d['id'] == dialog_id), None)
            if not target_dialog:
                self.log("Целевой чат не найден")
                return
                
            target_entity = target_dialog['entity']
            source_chat = self.source_entry.get()
            hours = int(self.hours_var.get())
            
            # Получаем сообщения
            self.log("Сбор сообщений...")
            messages = await get_chat_messages(self.client, source_chat, hours)
            
            if not messages:
                self.log("Нет сообщений для обработки")
                return
                
            # Генерируем саммари
            self.log("Генерация саммари...")
            config = load_config(self.config_var.get())
            openai_client = openai.AsyncOpenAI(api_key=config.openai_api_key)
            summary = await self.generate_summary(messages, openai_client)
            
            # Отправляем результат
            self.log("Отправка саммари...")
            await self.client.send_message(
                target_entity,
                f"📝 Саммари чата {source_chat} за последние {hours} часов:\n\n{summary}"
            )
            
            self.log("Саммари успешно отправлено!")
            
        except Exception as e:
            self.log(f"Ошибка: {e}")
            
    def start_summarization(self):
        """Запуск процесса создания саммари"""
        self.progress.start()
        self.start_btn.state(['disabled'])
        
        async def run():
            try:
                await self.summarize()
            finally:
                self.progress.stop()
                self.start_btn.state(['!disabled'])
            
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    async def generate_summary(self, messages: List[str], openai_client) -> str:
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
        user_prompt = self.user_prompt.get('1.0', tk.END).strip()
        
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

    def run(self):
        """Запуск приложения"""
        def run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
            
        # Запускаем event loop в отдельном потоке
        self.loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
        
        try:
            self.root.mainloop()
        finally:
            self.cleanup()
            # Ждем завершения потока loop
            if hasattr(self, 'loop_thread'):
                self.loop_thread.join(timeout=5)

    def filter_dialogs(self, *args):
        """Фильтрация и сортировка диалогов"""
        if not hasattr(self, 'dialogs'):
            return
            
        # Очищаем текущий список
        for item in self.dialogs_tree.get_children():
            self.dialogs_tree.delete(item)
            
        # Получаем текст поиска
        search_text = self.search_var.get().lower()
        
        # Создаем структуру папок
        folders = {}
        
        for dialog in self.dialogs:
            # Проверяем соответствие фильтрам
            if not self._dialog_matches_filters(dialog):
                continue
                
            # Проверяем соответствие поиску
            if search_text and search_text not in dialog['name'].lower():
                continue
                
            # Получаем папку диалога
            folder = dialog.get('folder', 'Без папки')
            
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(dialog)
        
        # Сортируем и отображаем
        sort_key = self.sort_var.get()
        
        for folder, folder_dialogs in sorted(folders.items()):
            # Создаем узел папки
            folder_id = self.dialogs_tree.insert('', 'end', text=folder, values=('', '', ''))
            
            # Сортируем диалоги в папке
            sorted_dialogs = self._sort_dialogs(folder_dialogs, sort_key)
            
            # Добавляем диалоги
            for dialog in sorted_dialogs:
                self.dialogs_tree.insert(folder_id, 'end', text=dialog['name'],
                                       values=(dialog['type'], 
                                              dialog.get('folder', ''),
                                              dialog['id']))  # Добавляем id в скрытую колонку

    def _dialog_matches_filters(self, dialog):
        """Проверка соответствия диалога текущим фильтрам"""
        dialog_type = dialog['type']
        if dialog_type == "Канал" and not self.show_channels.get():
            return False
        if dialog_type == "Чат" and not self.show_groups.get():
            return False
        if dialog_type == "Личка" and not self.show_private.get():
            return False
        return True

    def _sort_dialogs(self, dialogs, sort_key):
        """Сортировка диалогов"""
        if sort_key == "имя":
            return sorted(dialogs, key=lambda x: x['name'].lower())
        elif sort_key == "тип":
            return sorted(dialogs, key=lambda x: (x['type'], x['name'].lower()))
        elif sort_key == "папка":
            return sorted(dialogs, key=lambda x: (x.get('folder', ''), x['name'].lower()))
        return dialogs

if __name__ == "__main__":
    root = tk.Tk()
    app = TelegramSummarizerGUI(root)
    
    # Обработчик закрытия окна
    def on_closing():
        app.root.quit()
        app.root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    app.run() 