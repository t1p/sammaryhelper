import os
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import asyncio
import threading
from functools import partial
from typing import List, Dict, Any
from .telegram_client import TelegramClientManager
from .ai_handler import AIChatManager
from .utils import load_config, get_config_files, load_settings, save_settings
import openai
from telethon.tl.types import Channel  # Добавляем импорт в начало файла
from telethon import TelegramClient
import json

class TelegramSummarizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram Channel Summarizer")
        self.root.geometry("900x700")
        
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.loop = asyncio.new_event_loop()
        self.running = True
        
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.main_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.main_frame, text="Основное")
        
        self.config_frame = ttk.Frame(self.notebook, padding="10")  # Новая вкладка
        self.notebook.add(self.config_frame, text="Конфиг")
        
        self.settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.settings_frame, text="Настройки")
        
        # Загружаем настройки перед созданием интерфейса
        self.settings = {
            'openai_model': 'gpt-3.5-turbo',
            'system_prompt': 'Ты - помощник, который создает краткие и информативные саммари дискуссий.',
            'available_models': [
                'gpt-3.5-turbo',
                'gpt-4',
                'gpt-4-turbo-preview'
            ],
            'last_config': None
        }
        
        # Загружаем сохраненные настройки
        saved_settings = load_settings(self.app_dir)
        self.settings.update(saved_settings)
        
        # Устанавливаем состояние чекбокса "Дебаг"
        self.debug_var = tk.BooleanVar(value=self.settings.get('debug', False))
        
        self.setup_main_tab()
        self.setup_config_tab()  # Добавляем настройку новой вкладки
        self.setup_settings_tab()
        
        # Инициализируем client_manager
        config_name = self.config_var.get()
        self.settings['last_config'] = config_name
        self.save_settings()
        
        self.client_manager = TelegramClientManager({
            'config_name': config_name,
            'app_dir': self.app_dir
        })
        self.ai_manager = AIChatManager(self.settings)
        self.dialogs = []
        self.messages = []  # Добавляем атрибут для хранения сообщений
        
        self.config_combo.bind('<<ComboboxSelected>>', self.on_config_change)
        
        # Загружаем состояние окна
        self.load_window_state()
        
        # Привязываем событие закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_main_tab(self):
        """Настройка основной вкладки"""
        # Фильтры для диалогов
        self.dialogs_filter_frame = ttk.Frame(self.main_frame)
        self.dialogs_filter_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Поле поиска для диалогов
        ttk.Label(self.dialogs_filter_frame, text="Поиск диалогов:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.dialog_search_var = tk.StringVar()
        self.dialog_search_entry = ttk.Entry(self.dialogs_filter_frame, textvariable=self.dialog_search_var, width=20)
        self.dialog_search_entry.grid(row=0, column=1, padx=5, sticky=tk.W)
        
        # Выпадающее поле для сортировки диалогов
        ttk.Label(self.dialogs_filter_frame, text="Сортировка:").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.dialog_sort_var = tk.StringVar(value="name")
        self.dialog_sort_combo = ttk.Combobox(self.dialogs_filter_frame, textvariable=self.dialog_sort_var, state="readonly")
        self.dialog_sort_combo['values'] = ['name', 'type', 'folder']
        self.dialog_sort_combo.grid(row=0, column=3, padx=5, sticky=tk.W)
        
        # Поле для ограничения количества диалогов
        ttk.Label(self.dialogs_filter_frame, text="Макс. диалогов:").grid(row=1, column=0, padx=5, sticky=tk.W)
        self.max_dialogs_var = tk.StringVar(value="100")
        self.max_dialogs_entry = ttk.Entry(self.dialogs_filter_frame, textvariable=self.max_dialogs_var, width=5)
        self.max_dialogs_entry.grid(row=1, column=1, padx=5, sticky=tk.W)
        
        # Кнопка для загрузки диалогов
        self.load_dialogs_btn = ttk.Button(self.dialogs_filter_frame, text="Диалоги", 
                                           command=self.load_filtered_dialogs)
        self.load_dialogs_btn.grid(row=1, column=2, padx=5, sticky=tk.W)
        
        # Кнопка для фильтрации диалогов
        self.filter_dialogs_btn = ttk.Button(self.dialogs_filter_frame, text="Фильтровать", 
                                             command=self.apply_filter_to_loaded_dialogs)
        self.filter_dialogs_btn.grid(row=1, column=3, padx=5, sticky=tk.W)
        
        # Список диалогов (Treeview)
        self.dialogs_frame = ttk.Frame(self.main_frame)
        self.dialogs_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        self.dialogs_tree = ttk.Treeview(self.dialogs_frame, columns=('type', 'folder', 'id'), show='tree headings')
        self.dialogs_tree.heading('type', text='Тип')
        self.dialogs_tree.heading('folder', text='Папка')
        self.dialogs_tree.column('type', width=100)
        self.dialogs_tree.column('folder', width=100)
        self.dialogs_tree.column('id', width=0, stretch=False)
        
        scrollbar = ttk.Scrollbar(self.dialogs_frame, orient=tk.VERTICAL, command=self.dialogs_tree.yview)
        self.dialogs_tree.configure(yscrollcommand=scrollbar.set)
        
        self.dialogs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Фильтры для сообщений
        self.messages_filter_frame = ttk.Frame(self.main_frame)
        self.messages_filter_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Поле поиска для сообщений
        ttk.Label(self.messages_filter_frame, text="Поиск сообщений:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.messages_filter_frame, textvariable=self.search_var, width=20)
        self.search_entry.grid(row=0, column=1, padx=5, sticky=tk.W)
        
        # Чекбоксы для типов сообщений
        self.photo_var = tk.BooleanVar()
        self.video_var = tk.BooleanVar()
        ttk.Checkbutton(self.messages_filter_frame, text="Фото", variable=self.photo_var).grid(row=0, column=2, padx=5, sticky=tk.W)
        ttk.Checkbutton(self.messages_filter_frame, text="Видео", variable=self.video_var).grid(row=0, column=3, padx=5, sticky=tk.W)
        
        # Выпадающее поле для сортировки сообщений
        ttk.Label(self.messages_filter_frame, text="Сортировка:").grid(row=1, column=0, padx=5, sticky=tk.W)
        self.sort_var = tk.StringVar(value="date")
        self.sort_combo = ttk.Combobox(self.messages_filter_frame, textvariable=self.sort_var, state="readonly")
        self.sort_combo['values'] = ['date', 'sender', 'text']
        self.sort_combo.grid(row=1, column=1, padx=5, sticky=tk.W)
        
        # Поле для ограничения количества сообщений
        ttk.Label(self.messages_filter_frame, text="Макс. сообщений:").grid(row=1, column=2, padx=5, sticky=tk.W)
        self.max_messages_var = tk.StringVar(value="100")
        self.max_messages_entry = ttk.Entry(self.messages_filter_frame, textvariable=self.max_messages_var, width=5)
        self.max_messages_entry.grid(row=1, column=3, padx=5, sticky=tk.W)
        
        # Кнопка для загрузки сообщений
        self.load_messages_btn = ttk.Button(self.messages_filter_frame, text="Сообщения", 
                                            command=self.load_filtered_messages)
        self.load_messages_btn.grid(row=1, column=4, padx=5, sticky=tk.W)
        
        # Кнопка для фильтрации сообщений
        self.filter_messages_btn = ttk.Button(self.messages_filter_frame, text="Фильтровать", 
                                              command=self.apply_filter_to_loaded_messages)
        self.filter_messages_btn.grid(row=1, column=5, padx=5, sticky=tk.W)
        
        # Список сообщений (Treeview)
        self.messages_frame = ttk.Frame(self.main_frame)
        self.messages_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        self.messages_tree = ttk.Treeview(self.messages_frame, columns=('id', 'sender', 'text', 'date'), show='headings')
        self.messages_tree.heading('id', text='ID')
        self.messages_tree.heading('sender', text='Отправитель')
        self.messages_tree.heading('text', text='Сообщение')
        self.messages_tree.heading('date', text='Дата и время')
        self.messages_tree.column('id', width=50)
        self.messages_tree.column('sender', width=150)
        self.messages_tree.column('text', width=500)
        self.messages_tree.column('date', width=150)
        
        scrollbar = ttk.Scrollbar(self.messages_frame, orient=tk.VERTICAL, command=self.messages_tree.yview)
        self.messages_tree.configure(yscrollcommand=scrollbar.set)
        
        self.messages_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Поле для отображения полного текста сообщения
        self.full_message_text = scrolledtext.ScrolledText(self.main_frame, height=5, wrap=tk.WORD)
        self.full_message_text.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # Чат с ИИ
        chat_frame = ttk.LabelFrame(self.main_frame, text="Чат с ИИ", padding="5")
        chat_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # История чата
        self.chat_history = scrolledtext.ScrolledText(chat_frame, height=10, wrap=tk.WORD)
        self.chat_history.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Фрейм для ввода сообщения
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Поле ввода
        self.message_var = tk.StringVar()
        self.message_entry = ttk.Entry(input_frame, textvariable=self.message_var)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # Кнопка отправки
        self.send_btn = ttk.Button(input_frame, text="Отправить", command=self.send_message)
        self.send_btn.pack(side=tk.RIGHT)
        
        # Привязка Enter к отправке сообщения
        self.message_entry.bind('<Return>', lambda e: self.send_message())
        
        # Лог
        log_frame = ttk.LabelFrame(self.main_frame, text="Лог", padding="5")
        log_frame.grid(row=3, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Прогресс и подвал
        footer_frame = ttk.Frame(self.main_frame)
        footer_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.progress = ttk.Progressbar(footer_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, expand=True, padx=5)
        
        # Настройка растягивания
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(1, weight=1)
        self.main_frame.rowconfigure(2, weight=1)
        
        # Привязываем событие выбора сообщения
        self.messages_tree.bind('<<TreeviewSelect>>', self.on_message_select)
    
    def setup_config_tab(self):
        """Настройка вкладки конфига"""
        # Выбор конфига
        ttk.Label(self.config_frame, text="Выберите конфиг:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.config_var = tk.StringVar()
        self.config_combo = ttk.Combobox(self.config_frame, textvariable=self.config_var, state="readonly")
        configs = get_config_files(self.app_dir)
        self.config_combo['values'] = configs
        
        # Выбираем последний использованный конфиг или первый доступный
        if self.settings.get('last_config') in configs:
            self.config_combo.set(self.settings['last_config'])
        elif configs:
            self.config_combo.set(configs[0])
        
        self.config_combo.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Настройки API Telegram
        ttk.Label(self.config_frame, text="Telegram API:").grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(10,5))
        
        ttk.Label(self.config_frame, text="API ID:").grid(row=2, column=0, sticky=tk.W)
        self.api_id_var = tk.StringVar()
        self.api_id_entry = ttk.Entry(self.config_frame, textvariable=self.api_id_var)
        self.api_id_entry.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        ttk.Label(self.config_frame, text="API Hash:").grid(row=3, column=0, sticky=tk.W)
        self.api_hash_var = tk.StringVar()
        self.api_hash_entry = ttk.Entry(self.config_frame, textvariable=self.api_hash_var)
        self.api_hash_entry.grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        # Настройки прокси
        ttk.Label(self.config_frame, text="Прокси:").grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=(10,5))
        
        self.use_proxy_var = tk.BooleanVar()
        ttk.Checkbutton(self.config_frame, text="Использовать прокси", 
                        variable=self.use_proxy_var).grid(row=5, column=0, columnspan=3, sticky=tk.W)
        
        ttk.Label(self.config_frame, text="Тип:").grid(row=6, column=0, sticky=tk.W)
        self.proxy_type_var = tk.StringVar(value="socks5")
        proxy_type_combo = ttk.Combobox(self.config_frame, textvariable=self.proxy_type_var, 
                                       values=["socks5", "http", "https"])
        proxy_type_combo.grid(row=6, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        ttk.Label(self.config_frame, text="Хост:").grid(row=7, column=0, sticky=tk.W)
        self.proxy_host_var = tk.StringVar()
        ttk.Entry(self.config_frame, textvariable=self.proxy_host_var).grid(row=7, column=1, 
                  columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        ttk.Label(self.config_frame, text="Порт:").grid(row=8, column=0, sticky=tk.W)
        self.proxy_port_var = tk.StringVar()
        ttk.Entry(self.config_frame, textvariable=self.proxy_port_var).grid(row=8, column=1, 
                  columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        # OpenAI API
        ttk.Label(self.config_frame, text="OpenAI API:").grid(row=9, column=0, columnspan=3, sticky=tk.W, pady=(10,5))
        
        ttk.Label(self.config_frame, text="API Key:").grid(row=10, column=0, sticky=tk.W)
        self.openai_key_var = tk.StringVar()
        ttk.Entry(self.config_frame, textvariable=self.openai_key_var, show="*").grid(row=10, column=1, 
                  columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        # Кнопка сохранения
        self.save_config_btn = ttk.Button(self.config_frame, text="Сохранить конфиг", 
                                        command=self.save_config)
        self.save_config_btn.grid(row=11, column=0, columnspan=3, pady=20)
        
        # Загружаем текущие настройки конфига
        self.load_current_config()
        
        # Привязываем обработчик изменения конфига
        self.config_combo.bind('<<ComboboxSelected>>', self.on_config_change)

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
        
        # Дебаг
        ttk.Checkbutton(self.settings_frame, text="Дебаг", variable=self.debug_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Добавляем разделитель
        ttk.Separator(self.settings_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky='ew', pady=10)
        
        # Раздел версии клиента
        ttk.Label(self.settings_frame, text="Версия клиента:", font=('', 10, 'bold')).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(10,5))
        
        # System Version
        ttk.Label(self.settings_frame, text="Версия системы:").grid(row=6, column=0, sticky=tk.W)
        self.system_version_var = tk.StringVar(value=self.settings.get('system_version', 'Windows 10'))
        self.system_version_combo = ttk.Combobox(self.settings_frame, textvariable=self.system_version_var)
        self.system_version_combo['values'] = self.settings.get('system_versions', ['Windows 10', 'Android 13.0', 'iOS 16.5', 'macOS 13.4'])
        self.system_version_combo.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=5)
        
        # Device Model
        ttk.Label(self.settings_frame, text="Модель устройства:").grid(row=7, column=0, sticky=tk.W)
        self.device_model_var = tk.StringVar(value=self.settings.get('device_model', 'Desktop'))
        self.device_model_combo = ttk.Combobox(self.settings_frame, textvariable=self.device_model_var)
        self.device_model_combo['values'] = self.settings.get('device_models', ['Desktop', 'Samsung Galaxy S23', 'iPhone 14 Pro', 'MacBook Pro'])
        self.device_model_combo.grid(row=7, column=1, sticky=(tk.W, tk.E), padx=5)
        
        # App Version
        ttk.Label(self.settings_frame, text="Версия приложения:").grid(row=8, column=0, sticky=tk.W)
        self.app_version_var = tk.StringVar(value=self.settings.get('app_version', '4.8.1'))
        self.app_version_combo = ttk.Combobox(self.settings_frame, textvariable=self.app_version_var)
        self.app_version_combo['values'] = self.settings.get('app_versions', ['4.8.1', '9.6.3', '9.7.0'])
        self.app_version_combo.grid(row=8, column=1, sticky=(tk.W, tk.E), padx=5)
        
        # Кнопка применения версии клиента
        self.apply_version_btn = ttk.Button(self.settings_frame, text="Применить версию", 
                                          command=self.apply_client_version)
        self.apply_version_btn.grid(row=9, column=0, columnspan=2, pady=10)
        
        # Кнопка сохранения настроек
        self.save_settings_btn = ttk.Button(self.settings_frame, text="Сохранить настройки", command=self.save_settings)
        self.save_settings_btn.grid(row=10, column=0, columnspan=2, sticky=tk.W, pady=5)
    
    def load_settings(self):
        """Загрузка настроек из файла"""
        saved_settings = load_settings(self.app_dir)
        self.settings.update(saved_settings)
        
        if hasattr(self, 'model_var'):
            self.model_var.set(self.settings['openai_model'])
        if hasattr(self, 'system_prompt'):
            self.system_prompt.delete('1.0', tk.END)
            self.system_prompt.insert('1.0', self.settings['system_prompt'])
        if hasattr(self, 'debug_var'):
            self.debug_var.set(self.settings.get('debug', False))
    
    def save_settings(self):
        """Сохранение настроек в файл"""
        try:
            settings_path = os.path.join(self.app_dir, 'summarizer_settings.json')
            self.log(f"Попытка сохранения настроек в {settings_path}")
            
            # Обновляем настройки перед сохранением
            self.settings['openai_model'] = self.model_var.get()
            self.settings['system_prompt'] = self.system_prompt.get('1.0', tk.END).strip()
            self.settings['debug'] = self.debug_var.get()  # Обновляем состояние чекбокса "Дебаг"
            
            self.log(f"Настройки перед сохранением: {self.settings}")
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            
            self.log(f"Настройки сохранены: {self.settings}")
        except Exception as e:
            self.log(f"Ошибка при сохранении настроек: {e}")

    def run(self):
        """Запуск приложения"""
        def run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
            
        self.loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
        
        try:
            self.root.mainloop()
        finally:
            self.cleanup()
            if hasattr(self, 'loop_thread'):
                self.loop_thread.join(timeout=5)

    def get_participants(self):
        """Получение участников чата"""
        self.log("Начало получения участников чата...")
        self.progress.start()
        self.get_participants_btn.state(['disabled'])
        
        async def run():
            try:
                self.log("Проверка подключения клиента...")
                if not self.client_manager or not self.client_manager.client.is_connected():
                    self.log("Клиент не подключен, инициализация...")
                    if not await self.client_manager.init_client():
                        self.log("Ошибка инициализации клиента")
                        return
                        
                selected_items = self.dialogs_tree.selection()
                if not selected_items:
                    self.log("Не выбран целевой чат")
                    return
                    
                selected_item = selected_items[0]
                dialog_id = self.dialogs_tree.item(selected_item)['values'][2]
                self.log(f"Получение участников для чата с ID: {dialog_id}")
                
                participants = await self.client_manager.get_chat_participants(dialog_id)
                self.log(f"Участники чата: {len(participants)}")
                
                # Анализ участников с помощью ИИ
                self.log("Загрузка конфигурации для OpenAI...")
                config = self.load_config(self.config_var.get())
                openai_client = openai.AsyncOpenAI(api_key=config.openai_api_key)
                self.log("Анализ участников с помощью ИИ...")
                analysis = await self.ai_manager.analyze_participants(participants, openai_client)
                self.log(f"Анализ участников:\n{analysis}")
                
            except Exception as e:
                self.log(f"Ошибка: {e}")
            finally:
                self.progress.stop()
                self.get_participants_btn.state(['!disabled'])
                self.log("Завершение получения участников чата")
                
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    def filter_messages(self):
        """Фильтрация сообщений"""
        self.progress.start()
        self.filter_messages_btn.state(['disabled'])
        
        async def run():
            try:
                if not self.client_manager or not self.client_manager.client.is_connected():
                    if not await self.client_manager.init_client():
                        return
                        
                selected_items = self.dialogs_tree.selection()
                if not selected_items:
                    self.log("Не выбран целевой чат")
                    return
                    
                selected_item = selected_items[0]
                dialog_id = self.dialogs_tree.item(selected_item)['values'][2]
                
                # Получаем фильтры от пользователя
                filters = {
                    'search': self.search_var.get(),
                    'limit': int(self.max_messages_var.get()),
                    'filter': None
                }
                
                if self.photo_var.get():
                    filters['filter'] = 'photo'
                elif self.video_var.get():
                    filters['filter'] = 'video'
                
                if self.settings.get('debug', False):
                    self.log(f"Фильтры: {filters}")
                
                messages = await self.client_manager.filter_messages(dialog_id, filters)
                self.messages_tree.delete(*self.messages_tree.get_children())
                
                # Сортировка
                sort_key = self.sort_var.get()
                messages.sort(key=lambda x: x[sort_key])
                
                for message in messages:
                    sender = message.get('sender_name', 'Неизвестно')
                    text = message['text'].replace('\n', ' ')
                    date = message['date'].strftime('%Y-%m-%d %H:%M:%S')
                    self.messages_tree.insert('', 'end', values=(message['id'], sender, text, date))
                
                self.log(f"Найдено сообщений: {len(messages)}")
                
            except Exception as e:
                self.log(f"Ошибка: {e}")
            finally:
                self.progress.stop()
                self.filter_messages_btn.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    def on_config_change(self, event):
        """Обработчик изменения конфига"""
        self.progress.start()
        config_name = self.config_var.get()
        
        # Сохраняем выбранный конфиг
        self.settings['last_config'] = config_name
        self.save_settings()
        
        async def reconnect():
            try:
                # Отключаем старый клиент
                if hasattr(self, 'client_manager') and self.client_manager is not None:
                    if hasattr(self.client_manager, 'client') and self.client_manager.client is not None:
                        if self.client_manager.client.is_connected():
                            await self.client_manager.client.disconnect()
                
                # Создаем новый клиент
                self.client_manager = TelegramClientManager({
                    'config_name': config_name,
                    'app_dir': self.app_dir
                })
                
                # Очищаем список диалогов
                self.dialogs = []
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                self.log(f"Выбран конфиг: {config_name}")
                
                # Пробуем инициализировать клиент
                await self.client_manager.init_client()
                
            except Exception as e:
                self.log(f"Ошибка при смене конфига: {e}")
            finally:
                self.progress.stop()
        
        asyncio.run_coroutine_threadsafe(reconnect(), self.loop)

    def log(self, message: str):
        """Логирование сообщений"""
        if self.debug_var.get():
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)

    def cleanup(self):
        """Очистка ресурсов при закрытии приложения"""
        self.running = False
        
        async def cleanup_async():
            if hasattr(self, 'client_manager') and self.client_manager is not None:
                if hasattr(self.client_manager, 'client') and self.client_manager.client is not None:
                    if self.client_manager.client.is_connected():
                        await self.client_manager.client.disconnect()
        
        try:
            future = asyncio.run_coroutine_threadsafe(cleanup_async(), self.loop)
            future.result(timeout=5)
            
            self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception as e:
            if hasattr(self, 'log_text'):
                self.log_text.insert(tk.END, f"Ошибка при очистке ресурсов: {e}\n")
            else:
                print(f"Ошибка при очистке ресурсов: {e}")

    def load_filtered_dialogs(self):
        """Загрузка диалогов с учетом текущего фильтра"""
        self.progress.start()
        self.load_dialogs_btn.state(['disabled'])
        
        async def run():
            try:
                # Проверяем и инициализируем клиент, если необходимо
                if not self.client_manager:
                    self.client_manager = TelegramClientManager({
                        'config_name': self.config_var.get(),
                        'app_dir': self.app_dir
                    })
                
                if not self.client_manager.client or not self.client_manager.client.is_connected():
                    if not await self.client_manager.init_client():
                        self.log("Ошибка: клиент не инициализирован")
                        return
                
                # Получаем фильтры от пользователя
                filters = {
                    'search': self.dialog_search_var.get(),
                    'limit': int(self.max_dialogs_var.get()),
                    'sort': self.dialog_sort_var.get()
                }
                
                self.dialogs = await self.client_manager.filter_dialogs(filters)
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                
                for dialog in self.dialogs:
                    folder_name = f"Папка {dialog['folder_id']}" if dialog['folder_id'] is not None else "Без папки"
                    self.dialogs_tree.insert('', 'end', text=dialog['name'], values=(dialog['type'], folder_name, dialog['id']))
                
                self.log(f"Диалоги загружены: {len(self.dialogs)}")
            except Exception as e:
                self.log(f"Ошибка при загрузке диалогов: {e}")
            finally:
                self.progress.stop()
                self.load_dialogs_btn.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    def apply_filter_to_loaded_dialogs(self):
        """Применение фильтра к уже загруженным диалогам"""
        self.progress.start()
        self.filter_dialogs_btn.state(['disabled'])
        
        try:
            # Получаем фильтры от пользователя
            search_filter = self.dialog_search_var.get().lower()
            sort_key = self.dialog_sort_var.get()
            
            # Логируем полученные фильтры
            self.log(f"Применение фильтра: поиск='{search_filter}', сортировка='{sort_key}'")
            
            filtered_dialogs = [
                dialog for dialog in self.dialogs
                if search_filter in dialog['name'].lower()
            ]
            
            # Логируем список диалогов перед сортировкой
            self.log(f"Диалоги перед сортировкой: {filtered_dialogs}")
            
            if sort_key == 'folder':
                filtered_dialogs.sort(key=lambda x: x['folder_id'] if x['folder_id'] is not None else -1)
            else:
                filtered_dialogs.sort(key=lambda x: x[sort_key])
            
            # Логируем список диалогов после сортировки
            self.log(f"Диалоги после сортировки: {filtered_dialogs}")
            
            self.dialogs_tree.delete(*self.dialogs_tree.get_children())
            
            for dialog in filtered_dialogs:
                folder_name = f"Папка {dialog['folder_id']}" if dialog['folder_id'] is not None else "Без папки"
                self.dialogs_tree.insert('', 'end', text=dialog['name'], values=(dialog['type'], folder_name, dialog['id']))
            
            self.log(f"Диалоги отфильтрованы: {len(filtered_dialogs)}")
        except Exception as e:
            self.log(f"Ошибка при фильтрации диалогов: {e}")
        finally:
            self.progress.stop()
            self.filter_dialogs_btn.state(['!disabled'])

    def load_current_config(self):
        """Загрузка текущего конфига"""
        try:
            config_name = self.config_var.get()
            config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
            config = load_config(config_path)
            
            # Заполняем поля значениями из конфига
            self.api_id_var.set(str(getattr(config, 'api_id', '')))
            self.api_hash_var.set(getattr(config, 'api_hash', ''))
            self.openai_key_var.set(getattr(config, 'openai_api_key', ''))
            
            # Настройки прокси
            self.use_proxy_var.set(getattr(config, 'use_proxy', False))
            if hasattr(config, 'proxy_settings'):
                self.proxy_type_var.set(config.proxy_settings.get('proxy_type', 'socks5'))
                self.proxy_host_var.set(config.proxy_settings.get('proxy_host', ''))
                self.proxy_port_var.set(str(config.proxy_settings.get('proxy_port', '')))
            
        except Exception as e:
            self.log(f"Ошибка при загрузке конфига: {e}")

    def save_config(self):
        """Сохранение конфига"""
        try:
            config_name = self.config_var.get()
            config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
            
            config_content = f"""# Telegram API credentials
api_id = {self.api_id_var.get()}
api_hash = '{self.api_hash_var.get()}'

# Proxy settings
use_proxy = {str(self.use_proxy_var.get())}
proxy_settings = {{
    'proxy_type': '{self.proxy_type_var.get()}',
    'proxy_host': '{self.proxy_host_var.get()}',
    'proxy_port': {self.proxy_port_var.get() or 0}
}}

# OpenAI API key
openai_api_key = '{self.openai_key_var.get()}'
"""
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            self.log(f"Конфиг {config_name} успешно сохранен")
            
        except Exception as e:
            self.log(f"Ошибка при сохранении конфига: {e}")

    def send_message(self):
        """Отправка сообщения в чат"""
        message = self.message_var.get().strip()
        if not message:
            return
        
        self.message_var.set('')  # Очищаем поле ввода
        self.chat_history.insert(tk.END, f"Вы: {message}\n")
        self.chat_history.see(tk.END)
        
        self.progress.start()
        self.send_btn.state(['disabled'])
        self.message_entry.state(['disabled'])
        
        async def process_message():
            try:
                # Загружаем конфиг для OpenAI
                config_name = self.config_var.get()
                config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
                config = load_config(config_path)
                
                # Создаем клиент OpenAI
                openai_client = openai.AsyncOpenAI(api_key=config.openai_api_key)
                
                # Собираем контекст из выбранных сообщений
                selected_messages = [self.messages_tree.item(item)['values'][2] for item in self.messages_tree.selection()]
                context = "\n".join(selected_messages)
                
                # Отправляем запрос
                response = await openai_client.chat.completions.create(
                    model=self.settings['openai_model'],
                    messages=[
                        {"role": "system", "content": self.settings['system_prompt']},
                        {"role": "user", "content": f"{context}\n{message}"}
                    ]
                )
                
                # Получаем ответ
                ai_response = response.choices[0].message.content
                self.chat_history.insert(tk.END, f"ИИ: {ai_response}\n\n")
                self.chat_history.see(tk.END)
                
            except Exception as e:
                self.log(f"Ошибка при обработке сообщения: {e}")
                self.chat_history.insert(tk.END, f"Ошибка: {str(e)}\n\n")
                self.chat_history.see(tk.END)
            finally:
                self.progress.stop()
                self.send_btn.state(['!disabled'])
                self.message_entry.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(process_message(), self.loop)

    def load_filtered_messages(self):
        """Загрузка сообщений с учетом текущего фильтра"""
        self.progress.start()
        self.load_messages_btn.state(['disabled'])
        
        async def run():
            try:
                # Проверяем и инициализируем клиент, если необходимо
                if not self.client_manager or not self.client_manager.client.is_connected():
                    self.log("Клиент не подключен, инициализация...")
                    if not await self.client_manager.init_client():
                        self.log("Ошибка: клиент не инициализирован")
                        return
                
                selected_items = self.dialogs_tree.selection()
                if not selected_items:
                    self.log("Не выбран целевой чат")
                    return
                    
                selected_item = selected_items[0]
                dialog_id = self.dialogs_tree.item(selected_item)['values'][2]
                
                # Получаем фильтры от пользователя
                filters = {
                    'search': self.search_var.get(),
                    'limit': int(self.max_messages_var.get()),
                    'filter': 'photo' if self.photo_var.get() else 'video' if self.video_var.get() else None,
                    'sort': self.sort_var.get()
                }
                
                self.messages = await self.client_manager.filter_messages(dialog_id, filters)
                self.messages_tree.delete(*self.messages_tree.get_children())
                
                for message in self.messages:
                    sender = message.get('sender_name', 'Неизвестно')
                    text = message['text'].replace('\n', ' ')
                    date = message['date'].strftime('%Y-%m-%d %H:%M:%S')
                    self.messages_tree.insert('', 'end', values=(message['id'], sender, text, date))
                
                self.log(f"Сообщения загружены: {len(self.messages)}")
            except Exception as e:
                self.log(f"Ошибка при загрузке сообщений: {e}")
            finally:
                self.progress.stop()
                self.load_messages_btn.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    def apply_filter_to_loaded_messages(self):
        """Применение фильтра к уже загруженным сообщениям"""
        self.progress.start()
        self.filter_messages_btn.state(['disabled'])
        
        try:
            # Получаем фильтры от пользователя
            search_filter = self.search_var.get().lower()
            sort_key = self.sort_var.get()
            
            filtered_messages = [
                message for message in self.messages
                if search_filter in message['text'].lower()
            ]
            
            filtered_messages.sort(key=lambda x: x[sort_key])
            
            self.messages_tree.delete(*self.messages_tree.get_children())
            
            for message in filtered_messages:
                sender = message.get('sender_name', 'Неизвестно')
                text = message['text'].replace('\n', ' ')
                date = message['date'].strftime('%Y-%m-%d %H:%M:%S')
                self.messages_tree.insert('', 'end', values=(message['id'], sender, text, date))
            
            self.log(f"Сообщения отфильтрованы: {len(filtered_messages)}")
        except Exception as e:
            self.log(f"Ошибка при фильтрации сообщений: {e}")
        finally:
            self.progress.stop()
            self.filter_messages_btn.state(['!disabled'])

    def on_message_select(self, event):
        """Обработчик выбора сообщения"""
        selected_items = self.messages_tree.selection()
        if not selected_items:
            return
        
        selected_item = selected_items[0]
        message_text = self.messages_tree.item(selected_item)['values'][2]
        
        # Отображаем полный текст сообщения
        self.full_message_text.delete('1.0', tk.END)
        self.full_message_text.insert(tk.END, message_text)

    def filter_dialogs(self):
        """Фильтрация диалогов"""
        self.progress.start()
        self.filter_dialogs_btn.state(['disabled'])
        
        async def run():
            try:
                if not self.client_manager or not self.client_manager.client.is_connected():
                    if not await self.client_manager.init_client():
                        self.log("Ошибка: клиент не инициализирован")
                        return
                
                # Получаем фильтры от пользователя
                filters = {
                    'search': self.dialog_search_var.get(),
                    'limit': int(self.max_dialogs_var.get()),
                    'sort': self.dialog_sort_var.get()
                }
                
                self.dialogs = await self.client_manager.filter_dialogs(filters)
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                
                for dialog in self.dialogs:
                    self.dialogs_tree.insert('', 'end', text=dialog['name'], values=(dialog['type'], '', dialog['id']))
                
                self.log(f"Диалоги загружены: {len(self.dialogs)}")
            except Exception as e:
                self.log(f"Ошибка при фильтрации диалогов: {e}")
            finally:
                self.progress.stop()
                self.filter_dialogs_btn.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(run(), self.loop)

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

            # Создаем клиент
            self.client = TelegramClient(
                session_name,
                config.api_id,
                config.api_hash
            )

            # Подключаемся
            await self.client.connect()
            if not await self.client.is_user_authorized():
                await self.client.start()

            return True

        except Exception as e:
            self.log(f"Ошибка при инициализации клиента: {str(e)}")
            return False

    def load_window_state(self):
        """Загрузка состояния окна"""
        try:
            settings_path = os.path.join(self.app_dir, 'summarizer_settings.json')
            self.log(f"Попытка загрузки состояния окна из {settings_path}")
            
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                state = settings.get('window_state', {})
                if 'geometry' in state:
                    self.root.geometry(state['geometry'])
                    self.log(f"Состояние окна загружено: {state}")
                else:
                    self.log("Состояние окна не найдено, используются значения по умолчанию.")
                self.root.update_idletasks()
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            self.log(f"Ошибка при загрузке состояния окна: {e}")

    def save_window_state(self):
        """Сохранение состояния окна"""
        try:
            settings_path = os.path.join(self.app_dir, 'summarizer_settings.json')
            self.log(f"Попытка сохранения состояния окна в {settings_path}")
            
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                settings = {}
                self.log("Создание нового файла настроек.")
            
            geometry = self.root.geometry()
            self.log(f"Текущая геометрия окна: {geometry}")
            
            settings['window_state'] = {
                'geometry': geometry
            }
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            self.log(f"Состояние окна сохранено: {settings['window_state']}")
        except Exception as e:
            self.log(f"Ошибка при сохранении состояния окна: {e}")
    
    def on_close(self):
        """Обработчик закрытия окна"""
        self.log("Закрытие окна")  # Логируем начало закрытия
        self.save_settings()  # Сохраняем настройки перед закрытием
        self.root.destroy()

    def apply_client_version(self):
        """Применение новой версии клиента"""
        self.progress.start()
        self.apply_version_btn.state(['disabled'])
        
        async def reconnect():
            try:
                # Отключаем старый клиент
                if hasattr(self, 'client_manager') and self.client_manager is not None:
                    if hasattr(self.client_manager, 'client') and self.client_manager.client is not None:
                        if self.client_manager.client.is_connected():
                            await self.client_manager.client.disconnect()
                
                # Создаем новый клиент с новыми параметрами
                self.client_manager = TelegramClientManager({
                    'config_name': self.config_var.get(),
                    'app_dir': self.app_dir,
                    'system_version': self.system_version_var.get(),
                    'device_model': self.device_model_var.get(),
                    'app_version': self.app_version_var.get()
                })
                
                # Очищаем список диалогов
                self.dialogs = []
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                
                # Пробуем инициализировать клиент
                await self.client_manager.init_client()
                self.log("Версия клиента успешно обновлена")
                
            except Exception as e:
                self.log(f"Ошибка при обновлении версии клиента: {e}")
            finally:
                self.progress.stop()
                self.apply_version_btn.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(reconnect(), self.loop) 