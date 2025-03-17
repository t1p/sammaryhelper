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

# Примечание: Создание директории configs теперь является ответственностью DatabaseHandler
# и больше не обрабатывается в GUI. Это обеспечивает правильное разделение ответственности.

class TelegramSummarizerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram Channel Summarizer")
        self.root.geometry("900x700")
        
        # Настройка стиля приложения
        self.setup_styles()
        
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
            'last_config': None,
            'max_dialogs': '100',
            'max_messages': '100'
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
            'config_name': self.config_var.get(),
            'app_dir': self.app_dir,
            'debug': self.debug_var.get(),
            'config_format': 'json',
            'configs_in_parent_dir': False
        })
        self.ai_manager = AIChatManager(self.settings)
        self.dialogs = []
        self.messages = []  # Добавляем атрибут для хранения сообщений
        
        self.config_combo.bind('<<ComboboxSelected>>', self.on_config_change)
        
        # Загружаем состояние окна
        self.load_window_state()
        
        # Привязываем событие закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_styles(self):
        """Настройка стилей для улучшения внешнего вида"""
        style = ttk.Style()
        
        # Основной стиль приложения
        style.configure('TFrame', background='#f0f0f0')
        style.configure('TLabel', background='#f0f0f0', font=('Arial', 10))
        style.configure('TButton', font=('Arial', 10))
        
        # Стиль для LabelFrame с выраженной рамкой
        style.configure('TLabelframe', background='#f0f0f0', borderwidth=2)
        style.configure('TLabelframe.Label', font=('Arial', 11, 'bold'), background='#f0f0f0')
        
        # Стиль для PanedWindow
        style.configure('TPanedwindow', background='#e0e0e0', sashwidth=5)
        
        # Стиль для Treeview
        style.configure('Treeview', background='#ffffff', font=('Arial', 10))
        style.configure('Treeview.Heading', font=('Arial', 10, 'bold'))
    
    def setup_main_tab(self):
        """Настройка основной вкладки"""
        # Создаем основной PanedWindow для разделения интерфейса на части
        self.main_paned = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Левая панель для диалогов - используем LabelFrame вместо Frame
        self.dialogs_container = ttk.LabelFrame(self.main_paned, text="Диалоги")
        self.main_paned.add(self.dialogs_container, weight=1)
        
        # Правая панель для сообщений - используем LabelFrame вместо Frame
        self.messages_container = ttk.LabelFrame(self.main_paned, text="Содержимое")
        self.main_paned.add(self.messages_container, weight=2)
        
        # Вертикальный PanedWindow для разделения интерфейса сообщений и чата
        self.msg_paned = ttk.PanedWindow(self.messages_container, orient=tk.VERTICAL)
        self.msg_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # === НАСТРОЙКА СЕКЦИИ ДИАЛОГОВ ===
        
        # Фильтры для диалогов - делаем LabelFrame для выделения секции фильтров
        self.dialogs_filter_frame = ttk.LabelFrame(self.dialogs_container, text="Фильтры диалогов")
        self.dialogs_filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
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
        self.max_dialogs_var = tk.StringVar(value=self.settings.get('max_dialogs', '100'))
        self.max_dialogs_entry = ttk.Entry(self.dialogs_filter_frame, textvariable=self.max_dialogs_var, width=5)
        self.max_dialogs_entry.grid(row=1, column=1, padx=5, sticky=tk.W)
        
        # Кнопки в том же фрейме фильтрации диалогов
        self.load_dialogs_btn = ttk.Button(
            self.dialogs_filter_frame, 
            text="Загрузить диалоги", 
            command=self.load_filtered_dialogs
        )
        self.load_dialogs_btn.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        self.update_cache_btn = ttk.Button(
            self.dialogs_filter_frame,
            text="Обновить кеш",
            command=self.update_dialogs_cache
        )
        self.update_cache_btn.grid(row=2, column=2, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        # Список диалогов - делаем LabelFrame для выделения списка
        self.dialogs_frame = ttk.LabelFrame(self.dialogs_container, text="Список диалогов")
        self.dialogs_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.dialogs_tree = ttk.Treeview(self.dialogs_frame, columns=('name', 'type', 'folder', 'unread', 'id'), show='headings')
        self.dialogs_tree.heading('name', text='Название', command=lambda: self.treeview_sort_column(self.dialogs_tree, 'name', False))
        self.dialogs_tree.heading('type', text='Тип', command=lambda: self.treeview_sort_column(self.dialogs_tree, 'type', False))
        self.dialogs_tree.heading('folder', text='Папка', command=lambda: self.treeview_sort_column(self.dialogs_tree, 'folder', False))
        self.dialogs_tree.heading('unread', text='Непрочитано', command=lambda: self.treeview_sort_column(self.dialogs_tree, 'unread', False))
        self.dialogs_tree.heading('id', text='ID')
        self.dialogs_tree.column('name', width=200)
        self.dialogs_tree.column('type', width=100)
        self.dialogs_tree.column('folder', width=100)
        self.dialogs_tree.column('unread', width=100)
        self.dialogs_tree.column('id', width=50)
        
        scrollbar = ttk.Scrollbar(self.dialogs_frame, orient=tk.VERTICAL, command=self.dialogs_tree.yview)
        self.dialogs_tree.configure(yscrollcommand=scrollbar.set)
        
        self.dialogs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Добавляем обработчик выбора диалога
        self.dialogs_tree.bind('<<TreeviewSelect>>', self.on_dialog_select)
        
        # === НАСТРОЙКА СЕКЦИИ СООБЩЕНИЙ ===
        
        # Верхняя панель для списка сообщений
        self.messages_top_frame = ttk.Frame(self.msg_paned)
        self.msg_paned.add(self.messages_top_frame, weight=2)
        
        # Фрейм для фильтрации сообщений с явным заголовком
        self.messages_filter_frame = ttk.LabelFrame(self.messages_top_frame, text="Фильтры сообщений")
        self.messages_filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Поле для поиска сообщений
        ttk.Label(self.messages_filter_frame, text="Поиск:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.message_search_var = tk.StringVar()
        self.message_search_entry = ttk.Entry(self.messages_filter_frame, textvariable=self.message_search_var)
        self.message_search_entry.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        
        # Выпадающий список для фильтрации по типу медиа
        ttk.Label(self.messages_filter_frame, text="Фильтр:").grid(row=0, column=2, padx=5, sticky=tk.W)
        self.message_filter_var = tk.StringVar(value="all")
        self.message_filter_combo = ttk.Combobox(self.messages_filter_frame, textvariable=self.message_filter_var, state="readonly")
        self.message_filter_combo['values'] = ['all', 'photo', 'video']
        self.message_filter_combo.grid(row=0, column=3, padx=5, sticky=tk.W)
        
        # Выпадающий список для сортировки сообщений
        ttk.Label(self.messages_filter_frame, text="Сортировка:").grid(row=1, column=0, padx=5, sticky=tk.W)
        self.message_sort_var = tk.StringVar(value="date")
        self.message_sort_combo = ttk.Combobox(self.messages_filter_frame, textvariable=self.message_sort_var, state="readonly")
        self.message_sort_combo['values'] = ['date', 'sender']
        self.message_sort_combo.grid(row=1, column=1, padx=5, sticky=tk.W)
        
        # Поле для ограничения количества сообщений
        ttk.Label(self.messages_filter_frame, text="Макс. сообщений:").grid(row=1, column=2, padx=5, sticky=tk.W)
        self.max_messages_var = tk.StringVar(value=self.settings.get('max_messages', '100'))
        self.max_messages_entry = ttk.Entry(self.messages_filter_frame, textvariable=self.max_messages_var, width=5)
        self.max_messages_entry.grid(row=1, column=3, padx=5, sticky=tk.W)
        
        # Кнопка для загрузки сообщений
        self.load_messages_btn = ttk.Button(self.messages_filter_frame, text="Сообщения", command=self.load_messages)
        self.load_messages_btn.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky=tk.W)
        
        # Создаем PanedWindow для списка сообщений и просмотра текста
        self.messages_content_paned = ttk.PanedWindow(self.messages_top_frame, orient=tk.VERTICAL)
        self.messages_content_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Фрейм для списка сообщений с заголовком
        self.messages_frame = ttk.LabelFrame(self.messages_content_paned, text="Список сообщений")
        self.messages_content_paned.add(self.messages_frame, weight=2)
        
        # Treeview для отображения сообщений
        self.messages_tree = ttk.Treeview(self.messages_frame, columns=('id', 'sender', 'text', 'date'), show='headings')
        self.messages_tree.heading('id', text='ID', command=lambda: self.treeview_sort_column(self.messages_tree, 'id', False))
        self.messages_tree.heading('sender', text='Отправитель', command=lambda: self.treeview_sort_column(self.messages_tree, 'sender', False))
        self.messages_tree.heading('text', text='Сообщение', command=lambda: self.treeview_sort_column(self.messages_tree, 'text', False))
        self.messages_tree.heading('date', text='Дата', command=lambda: self.treeview_sort_column(self.messages_tree, 'date', False))
        self.messages_tree.column('id', width=50)
        self.messages_tree.column('sender', width=150)
        self.messages_tree.column('text', width=400)
        self.messages_tree.column('date', width=150)
        
        scrollbar = ttk.Scrollbar(self.messages_frame, orient=tk.VERTICAL, command=self.messages_tree.yview)
        self.messages_tree.configure(yscrollcommand=scrollbar.set)
        
        self.messages_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Добавляем обработчик выбора сообщения
        self.messages_tree.bind('<<TreeviewSelect>>', self.on_message_select)
        
        # Добавляем фрейм для просмотра полного текста сообщения в PanedWindow
        self.message_view_frame = ttk.LabelFrame(self.messages_content_paned, text="Текст сообщения")
        self.messages_content_paned.add(self.message_view_frame, weight=1)
        
        # Текстовое поле для отображения полного сообщения
        self.message_view = scrolledtext.ScrolledText(self.message_view_frame, wrap=tk.WORD, height=5)
        self.message_view.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Нижняя панель для чата с ИИ и логов
        self.bottom_frame = ttk.Frame(self.msg_paned)
        self.msg_paned.add(self.bottom_frame, weight=1)
        
        # Добавляем стилизацию для PanedWindow
        style = ttk.Style()
        style.configure('TPanedwindow', background='#eeeeee')
        
        # Улучшаем отображение разделителей
        style.configure('Sash', sashthickness=5, gripcount=5)
        
        # Дополнительный горизонтальный PanedWindow для нижней части
        self.bottom_paned = ttk.PanedWindow(self.bottom_frame, orient=tk.HORIZONTAL)
        self.bottom_paned.pack(fill=tk.BOTH, expand=True)
        
        # Фрейм для чата с ИИ (левая часть нижней панели)
        self.ai_chat_frame = ttk.LabelFrame(self.bottom_paned, text="Чат с ИИ")
        self.bottom_paned.add(self.ai_chat_frame, weight=1)
        
        # Создаем вертикальный PanedWindow для истории чата и поля ввода
        self.ai_chat_paned = ttk.PanedWindow(self.ai_chat_frame, orient=tk.VERTICAL)
        self.ai_chat_paned.pack(fill=tk.BOTH, expand=True)
        
        # Текстовое поле для чата с ИИ
        self.ai_chat = scrolledtext.ScrolledText(self.ai_chat_paned, wrap=tk.WORD)
        self.ai_chat_paned.add(self.ai_chat, weight=4)
        
        # Фрейм для поля ввода и кнопки
        self.ai_input_frame = ttk.Frame(self.ai_chat_paned)
        self.ai_chat_paned.add(self.ai_input_frame, weight=1)
        
        # Поле для ввода запроса к ИИ
        self.ai_input = ttk.Entry(self.ai_input_frame)
        self.ai_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        
        # Кнопка для отправки запроса
        self.send_to_ai_btn = ttk.Button(self.ai_input_frame, text="Отправить", command=self.send_to_ai)
        self.send_to_ai_btn.pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Фрейм для логов (правая часть нижней панели)
        self.log_frame = ttk.LabelFrame(self.bottom_paned, text="Лог")
        self.bottom_paned.add(self.log_frame, weight=1)
        
        # Текстовое поле для логов
        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Индикатор прогресса
        self.progress = ttk.Progressbar(self.main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, padx=5, pady=5)
    
    def setup_config_tab(self):
        """Настройка вкладки конфига"""
        # Выбор конфига
        ttk.Label(self.config_frame, text="Выберите конфиг:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.config_var = tk.StringVar(value=self.settings.get('last_config', ''))
        self.config_combo = ttk.Combobox(self.config_frame, textvariable=self.config_var, state="readonly")
        
        # Получаем список JSON и PY-файлов конфигурации
        configs_dir = os.path.join(self.app_dir, "configs")
        config_files = []
        try:
            config_files = [f.split('.')[0] for f in os.listdir(configs_dir) 
                            if f.endswith(('.json', '.py'))]
        except FileNotFoundError:
            self.log("Директория configs не существует. Будет создана DatabaseHandler'ом при необходимости.")
            
        self.config_combo['values'] = config_files
        
        # Устанавливаем значение по умолчанию, если оно есть
        if self.settings.get('last_config') in config_files:
            self.config_combo.set(self.settings.get('last_config'))
        elif config_files:
            self.config_combo.set(config_files[0])
        
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
        
        # Добавляем секцию настроек базы данных
        ttk.Label(self.config_frame, text="Настройки базы данных:", font=('', 10, 'bold')).grid(
            row=11, column=0, columnspan=3, sticky=tk.W, pady=(10,5))

        # Хост БД
        ttk.Label(self.config_frame, text="Хост:").grid(row=12, column=0, sticky=tk.W)
        self.db_host_var = tk.StringVar(value="localhost")
        ttk.Entry(self.config_frame, textvariable=self.db_host_var).grid(
            row=12, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        # Порт БД
        ttk.Label(self.config_frame, text="Порт:").grid(row=13, column=0, sticky=tk.W)
        self.db_port_var = tk.StringVar(value="5432")
        ttk.Entry(self.config_frame, textvariable=self.db_port_var).grid(
            row=13, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        # Имя базы данных
        ttk.Label(self.config_frame, text="База данных:").grid(row=14, column=0, sticky=tk.W)
        self.db_name_var = tk.StringVar(value="telegram_summarizer")
        ttk.Entry(self.config_frame, textvariable=self.db_name_var).grid(
            row=14, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        # Пользователь БД
        ttk.Label(self.config_frame, text="Пользователь:").grid(row=15, column=0, sticky=tk.W)
        self.db_user_var = tk.StringVar(value="postgres")
        ttk.Entry(self.config_frame, textvariable=self.db_user_var).grid(
            row=15, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        # Пароль БД
        ttk.Label(self.config_frame, text="Пароль:").grid(row=16, column=0, sticky=tk.W)
        self.db_password_var = tk.StringVar(value="postgres")
        ttk.Entry(self.config_frame, textvariable=self.db_password_var, show="*").grid(
            row=16, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5)
        
        # Кнопка сохранения
        self.save_config_btn = ttk.Button(self.config_frame, text="Сохранить конфиг", 
                                        command=self.save_config)
        self.save_config_btn.grid(row=17, column=0, columnspan=3, pady=20)
        
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
                dialog_id = self.dialogs_tree.item(selected_item)['values'][4]
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
                dialog_id = self.dialogs_tree.item(selected_item)['values'][4]
                
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
                # Загружаем конфигурацию для передачи настроек БД
                config_name = self.config_var.get()
                json_config_path = os.path.join(self.app_dir, "configs", f"{config_name}.json")
                py_config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
                
                db_settings = None
                if os.path.exists(json_config_path):
                    with open(json_config_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                        db_settings = config_data.get('db_settings', None)
                elif os.path.exists(py_config_path):
                    config = load_config(py_config_path)
                    db_settings = getattr(config, 'db_settings', None)
                
                self.client_manager = TelegramClientManager({
                    'config_name': config_name,
                    'app_dir': self.app_dir,
                    'debug': self.debug_var.get(),
                    'config_format': 'json',
                    'configs_in_parent_dir': False,
                    'db_settings': db_settings
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

    def log(self, message):
        """Логирование сообщений"""
        if self.debug_var.get():
            print(message)
        
        # Добавляем сообщение в лог-виджет, если он существует
        if hasattr(self, 'log_text') and self.log_text:
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
        """Загрузка и фильтрация диалогов"""
        self.progress.start()
        self.load_dialogs_btn.state(['disabled'])
        
        async def run():
            try:
                # Проверяем и инициализируем клиент, если необходимо
                if not self.client_manager:
                    self.client_manager = TelegramClientManager({
                        'config_name': self.config_var.get(),
                        'app_dir': self.app_dir,
                        'debug': self.debug_var.get()
                    })
                
                if not hasattr(self.client_manager, 'client') or not self.client_manager.client or not self.client_manager.client.is_connected():
                    if not await self.client_manager.init_client():
                        self.log("Ошибка: клиент не инициализирован")
                        return
                
                # Получаем фильтры от пользователя
                dialog_limit = self.max_dialogs_var.get()
                self.log(f"Значение поля max_dialogs_var: {dialog_limit}")
                
                try:
                    dialog_limit_int = int(dialog_limit)
                    self.log(f"Преобразовано в целое число: {dialog_limit_int}")
                except ValueError as e:
                    self.log(f"Ошибка преобразования лимита диалогов в число: {e}")
                    dialog_limit_int = 100  # Значение по умолчанию
                    self.log(f"Установлено значение по умолчанию: {dialog_limit_int}")
                
                filters = {
                    'search': self.dialog_search_var.get(),
                    'sort': self.dialog_sort_var.get(),
                    'limit': dialog_limit_int,
                    'force_refresh': False  # Не обновляем кеш при обычной загрузке
                }
                
                self.log(f"Применяемые фильтры для диалогов: {filters}")
                
                self.dialogs = await self.client_manager.filter_dialogs(filters)
                self.log(f"Получено диалогов после фильтрации: {len(self.dialogs)}")
                
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                
                for dialog in self.dialogs:
                    folder_name = f"Папка {dialog['folder_id']}" if dialog['folder_id'] is not None else "Без папки"
                    unread_count = dialog.get('unread_count', 0)
                    
                    # Выводим отладочную информацию
                    self.log(f"Добавление диалога: {dialog['name']}, ID: {dialog['id']}")
                    
                    self.dialogs_tree.insert('', 'end', values=(
                        dialog['name'], 
                        dialog['type'], 
                        folder_name, 
                        unread_count,
                        dialog['id']  # Важно: ID должен быть последним элементом
                    ))
                
                self.log(f"Диалоги загружены: {len(self.dialogs)}")
            except Exception as e:
                self.log(f"Ошибка при загрузке диалогов: {e}")
                import traceback
                self.log(traceback.format_exc())
            finally:
                self.progress.stop()
                self.load_dialogs_btn.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    def apply_filter_to_loaded_dialogs(self):
        """Применение фильтра к уже загруженным диалогам"""
        search_text = self.dialog_search_var.get().lower()
        
        # Очищаем список диалогов
        self.dialogs_tree.delete(*self.dialogs_tree.get_children())
        
        # Фильтруем диалоги
        filtered_dialogs = []
        for dialog in self.dialogs:
            if search_text and search_text not in dialog['name'].lower():
                continue
            filtered_dialogs.append(dialog)
        
        # Сортируем диалоги
        sort_by = self.dialog_sort_var.get()
        if sort_by == 'name':
            filtered_dialogs.sort(key=lambda d: d['name'])
        elif sort_by == 'type':
            filtered_dialogs.sort(key=lambda d: d['type'])
        elif sort_by == 'folder':
            filtered_dialogs.sort(key=lambda d: d.get('folder_id', 0) or 0)
        
        # Заполняем список диалогов
        for dialog in filtered_dialogs:
            folder_name = f"Папка {dialog['folder_id']}" if dialog['folder_id'] is not None else "Без папки"
            unread_count = dialog.get('unread_count', 0)
            
            self.dialogs_tree.insert('', 'end', values=(
                dialog['name'], 
                dialog['type'], 
                folder_name, 
                unread_count,
                dialog['id']  # Важно: ID должен быть последним элементом
            ))
        
        self.log(f"Диалоги отфильтрованы: {len(filtered_dialogs)}")

    def load_current_config(self):
        """Загрузка текущего конфига из JSON-файла или Python-модуля"""
        try:
            config_name = self.config_var.get()
            json_config_path = os.path.join(self.app_dir, "configs", f"{config_name}.json")
            py_config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
            
            # Сначала пробуем загрузить конфиг из JSON
            if os.path.exists(json_config_path):
                with open(json_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Заполняем поля значениями из конфига
                self.api_id_var.set(str(config.get('api_id', '')))
                self.api_hash_var.set(config.get('api_hash', ''))
                self.openai_key_var.set(config.get('openai_api_key', ''))
                
                # Настройки прокси
                self.use_proxy_var.set(config.get('use_proxy', False))
                if 'proxy_settings' in config:
                    proxy_settings = config['proxy_settings']
                    self.proxy_type_var.set(proxy_settings.get('proxy_type', 'socks5'))
                    self.proxy_host_var.set(proxy_settings.get('proxy_host', ''))
                    self.proxy_port_var.set(str(proxy_settings.get('proxy_port', '')))
                
                # Загружаем настройки базы данных
                if 'db_settings' in config:
                    db_settings = config['db_settings']
                    self.db_host_var.set(db_settings.get('host', 'localhost'))
                    self.db_port_var.set(str(db_settings.get('port', 5432)))
                    self.db_name_var.set(db_settings.get('database', 'telegram_summarizer'))
                    self.db_user_var.set(db_settings.get('user', 'postgres'))
                    self.db_password_var.set(db_settings.get('password', 'postgres'))
                
                self.log(f"Конфиг {config_name}.json успешно загружен")
                
            # Если JSON не найден, пробуем загрузить Python-модуль
            elif os.path.exists(py_config_path):
                config = load_config(py_config_path)
                
                # Заполняем поля значениями из Python-модуля
                self.api_id_var.set(str(getattr(config, 'api_id', '')))
                self.api_hash_var.set(getattr(config, 'api_hash', ''))
                self.openai_key_var.set(getattr(config, 'openai_api_key', ''))
                
                # Настройки прокси
                self.use_proxy_var.set(getattr(config, 'use_proxy', False))
                if hasattr(config, 'proxy_settings'):
                    self.proxy_type_var.set(config.proxy_settings.get('proxy_type', 'socks5'))
                    self.proxy_host_var.set(config.proxy_settings.get('proxy_host', ''))
                    self.proxy_port_var.set(str(config.proxy_settings.get('proxy_port', '')))
                
                # Загружаем настройки базы данных
                if hasattr(config, 'db_settings'):
                    db_settings = config.db_settings
                    self.db_host_var.set(db_settings.get('host', 'localhost'))
                    self.db_port_var.set(str(db_settings.get('port', 5432)))
                    self.db_name_var.set(db_settings.get('database', 'telegram_summarizer'))
                    self.db_user_var.set(db_settings.get('user', 'postgres'))
                    self.db_password_var.set(db_settings.get('password', 'postgres'))
                
                self.log(f"Конфиг {config_name}.py успешно загружен")
                
            else:
                self.log(f"Конфиг {config_name} не найден. Проверьте наличие файла .json или .py")
                
        except Exception as e:
            self.log(f"Ошибка при загрузке конфига: {e}")

    def save_config(self):
        """Сохранение конфига в формате JSON"""
        try:
            config_name = self.config_var.get()
            config_path = os.path.join(self.app_dir, "configs", f"{config_name}.json")
            
            # Формируем содержимое JSON-файла конфигурации
            config_data = {
                "api_id": int(self.api_id_var.get()) if self.api_id_var.get().isdigit() else 0,
                "api_hash": self.api_hash_var.get(),
                "use_proxy": self.use_proxy_var.get(),
                "proxy_settings": {
                    "proxy_type": self.proxy_type_var.get(),
                    "proxy_host": self.proxy_host_var.get(),
                    "proxy_port": int(self.proxy_port_var.get()) if self.proxy_port_var.get().isdigit() else 0
                },
                "openai_api_key": self.openai_key_var.get(),
                "db_settings": {
                    "host": self.db_host_var.get(),
                    "port": int(self.db_port_var.get()) if self.db_port_var.get().isdigit() else 5432,
                    "database": self.db_name_var.get(),
                    "user": self.db_user_var.get(),
                    "password": self.db_password_var.get()
                }
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            
            self.log(f"Конфиг {config_name} успешно сохранен в формате JSON")
            
        except Exception as e:
            self.log(f"Ошибка при сохранении конфига: {e}")

    def send_to_ai(self):
        """Отправка выбранных сообщений в AI"""
        # Получаем текст из поля ввода
        message = self.ai_input.get()
        if not message:
            self.log("Ошибка: пустой запрос к ИИ")
            return
        
        # Очищаем поле ввода
        self.ai_input.delete(0, tk.END)
        
        # Отображаем сообщение пользователя в чате
        self.ai_chat.insert(tk.END, f"Вы: {message}\n\n")
        self.ai_chat.see(tk.END)
        
        # Показываем индикатор прогресса
        self.progress.start()
        self.send_to_ai_btn.state(['disabled'])
        self.ai_input.state(['disabled'])
        
        async def process_ai_request():
            try:
                # Проверяем, что клиент инициализирован
                if not self.client_manager or not hasattr(self.client_manager, 'client') or not self.client_manager.client.is_connected():
                    if not await self.client_manager.init_client():
                        self.log("Ошибка: клиент не инициализирован")
                        return
                
                # Собираем контекст из выбранных сообщений
                selected_messages = []
                for item in self.messages_tree.selection():
                    item_data = self.messages_tree.item(item)
                    values = item_data['values']
                    if values and len(values) >= 3:
                        sender = values[1]
                        text = values[2]
                        date = values[3]
                        selected_messages.append(f"{sender} ({date}): {text}")
                
                context = "\n".join(selected_messages)
                
                self.log(f"Отправка запроса к ИИ: {message}")
                self.log(f"Контекст (выбрано {len(selected_messages)} сообщений)")
                
                # Используем AI-менеджер для получения ответа
                # Проверяем, есть ли API ключ в настройках
                if 'openai_api_key' not in self.settings:
                    # Получаем API ключ из конфига
                    config_name = self.config_var.get()
                    json_config_path = os.path.join(self.app_dir, "configs", f"{config_name}.json")
                    py_config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
                    
                    if os.path.exists(json_config_path):
                        with open(json_config_path, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                        self.settings['openai_api_key'] = config_data['openai_api_key']
                    elif os.path.exists(py_config_path):
                        config = load_config(py_config_path)
                        self.settings['openai_api_key'] = getattr(config, 'openai_api_key', '')
                
                # Получаем ответ от ИИ
                response = await self.ai_manager.get_response(
                    user_query=message, 
                    context=context
                )
                
                # Отображаем ответ в чате
                self.ai_chat.insert(tk.END, f"ИИ: {response}\n\n")
                self.ai_chat.see(tk.END)
                
            except Exception as e:
                self.log(f"Ошибка при отправке запроса к ИИ: {e}")
                import traceback
                self.log(traceback.format_exc())
                self.ai_chat.insert(tk.END, f"Ошибка: {str(e)}\n\n")
                self.ai_chat.see(tk.END)
            finally:
                self.progress.stop()
                self.send_to_ai_btn.state(['!disabled'])
                self.ai_input.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(process_ai_request(), self.loop)

    def load_messages(self):
        """Загрузка сообщений для выбранного диалога"""
        if not hasattr(self, 'selected_dialog_id') or self.selected_dialog_id is None:
            self.log("Ошибка: не выбран диалог")
            return
        
        self.log(f"Загрузка сообщений для диалога ID: {self.selected_dialog_id}")
        
        self.progress.start()
        self.load_messages_btn.state(['disabled'])
        
        async def run():
            try:
                # Проверяем, что клиент инициализирован
                if not self.client_manager or not hasattr(self.client_manager, 'client') or not self.client_manager.client.is_connected():
                    if not await self.client_manager.init_client():
                        self.log("Ошибка: клиент не инициализирован")
                        return
                
                # Получаем фильтры от пользователя
                filters = {
                    'search': self.message_search_var.get(),
                    'limit': int(self.max_messages_var.get()),
                    'filter': self.message_filter_var.get()
                }
                
                # Логируем запрос для отладки
                self.log(f"Загрузка сообщений для диалога {self.selected_dialog_id} с фильтрами: {filters}")
                
                # Загружаем сообщения
                messages = await self.client_manager.filter_messages(self.selected_dialog_id, filters)
                
                # Очищаем список сообщений
                self.messages_tree.delete(*self.messages_tree.get_children())
                
                # Заполняем список сообщений
                for message in messages:
                    # Проверяем тип поля date и форматируем соответственно
                    if isinstance(message['date'], str):
                        date_str = message['date']  # Если это уже строка, используем как есть
                    else:
                        # Если это объект datetime, форматируем его
                        date_str = message['date'].strftime('%Y-%m-%d %H:%M:%S')
                    
                    self.messages_tree.insert('', 'end', values=(
                        message['id'],
                        message['sender_name'],
                        message['text'][:100] + ('...' if len(message['text']) > 100 else ''),
                        date_str
                    ))
                
                # Сохраняем сообщения для последующей фильтрации
                self.messages = messages
                
                self.log(f"Сообщения загружены: {len(messages)}")
            except Exception as e:
                self.log(f"Ошибка при загрузке сообщений: {e}")
                import traceback
                self.log(traceback.format_exc())
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
            search_filter = self.message_search_var.get().lower()
            sort_key = self.message_sort_var.get()
            
            filtered_messages = [
                message for message in self.messages
                if search_filter in message['text'].lower()
            ]
            
            filtered_messages.sort(key=lambda x: x[sort_key])
            
            self.messages_tree.delete(*self.messages_tree.get_children())
            
            for message in filtered_messages:
                sender = message.get('sender_name', 'Неизвестно')
                text = message['text'].replace('\n', ' ')
                
                # Проверяем тип поля date и форматируем соответственно
                if isinstance(message['date'], str):
                    date = message['date']
                else:
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
        
        # Получаем ID выбранного сообщения
        message_id = self.messages_tree.item(selected_items[0])['values'][0]
        
        # Логируем для отладки
        self.log(f"Выбрано сообщение с ID: {message_id}")
        
        # Находим сообщение по ID в списке messages
        selected_message = None
        for message in self.messages:
            if str(message['id']) == str(message_id):  # Преобразуем оба к строке для сравнения
                selected_message = message
                break
        
        # Отображаем полный текст сообщения
        if selected_message:
            # Разрешаем редактирование
            self.message_view.config(state=tk.NORMAL)
            
            # Очищаем предыдущий текст
            self.message_view.delete(1.0, tk.END)
            
            # Собираем информацию о сообщении
            sender = selected_message.get('sender_name', 'Неизвестно')
            
            # Определяем, как форматировать дату
            if isinstance(selected_message['date'], str):
                date = selected_message['date']
            else:
                date = selected_message['date'].strftime('%Y-%m-%d %H:%M:%S')
            
            # Форматируем заголовок сообщения
            header = f"От: {sender}\nДата: {date}\n\n"
            
            # Вставляем информацию в текстовое поле
            self.message_view.insert(tk.END, header)
            self.message_view.insert(tk.END, selected_message['text'])
            
            # Делаем текстовое поле только для чтения
            self.message_view.config(state=tk.DISABLED)
            self.log(f"Отображено сообщение: {sender}, {date}")
        else:
            self.message_view.config(state=tk.NORMAL)
            self.message_view.delete(1.0, tk.END)
            self.message_view.insert(tk.END, f"Сообщение с ID {message_id} не найдено")
            self.message_view.config(state=tk.DISABLED)
            self.log(f"Ошибка: сообщение с ID {message_id} не найдено в списке из {len(self.messages)} сообщений")

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
            
            # Удаляем API ключ из настроек перед сохранением
            if 'openai_api_key' in settings:
                del settings['openai_api_key']
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            self.log(f"Состояние окна сохранено: {settings['window_state']}")
        except Exception as e:
            self.log(f"Ошибка при сохранении состояния окна: {e}")
    
    def on_close(self):
        """Обработчик закрытия окна"""
        self.log("Закрытие окна")  # Логируем начало закрытия
        
        # Обновляем настройки перед сохранением
        self.settings['openai_model'] = self.model_var.get()
        self.settings['system_prompt'] = self.system_prompt.get('1.0', tk.END).strip()
        self.settings['debug'] = self.debug_var.get()
        self.settings['max_dialogs'] = self.max_dialogs_var.get()
        self.settings['max_messages'] = self.max_messages_var.get()
        
        # Сохраняем настройки
        self.save_settings()
        
        # Сохраняем состояние окна
        self.save_window_state()
        
        # Закрываем окно
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

    def treeview_sort_column(self, tv, col, reverse):
        """Сортировка колонки в Treeview"""
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
        
        # Особая обработка для даты
        if col == 'date':
            # Пытаемся сортировать даты
            l.sort(reverse=reverse)
        else:
            try:
                # Пробуем сортировать как числа
                l.sort(key=lambda t: int(t[0]), reverse=reverse)
            except ValueError:
                # Если не получилось, сортируем как строки
                l.sort(reverse=reverse)
        
        # Переупорядочиваем элементы
        for index, (val, k) in enumerate(l):
            tv.move(k, '', index)
        
        # Меняем направление сортировки при следующем клике
        tv.heading(col, command=lambda: self.treeview_sort_column(tv, col, not reverse))

    def on_dialog_select(self, event):
        """Обработчик выбора диалога"""
        selected_items = self.dialogs_tree.selection()
        if not selected_items:
            return
        
        # Получаем ID выбранного диалога
        item = selected_items[0]
        values = self.dialogs_tree.item(item)['values']
        
        # Выводим отладочную информацию
        self.log(f"Выбран диалог: {values}")
        
        # Проверяем, что values содержит достаточно элементов
        if not values or len(values) < 5:
            self.log(f"Ошибка: не удалось получить ID диалога из {values}")
            return
        
        # ID находится в последней колонке
        dialog_id = values[4]
        
        # Проверяем, что dialog_id - это число
        try:
            dialog_id = int(dialog_id)
        except (ValueError, TypeError):
            self.log(f"Ошибка: некорректный ID диалога: {dialog_id}")
            return
        
        self.selected_dialog_id = dialog_id
        self.selected_dialog_name = values[0]  # Название диалога
        
        # Обновляем заголовки для лучшей визуализации контекста
        self.messages_filter_frame.configure(text=f"Фильтры сообщений: {self.selected_dialog_name}")
        self.messages_frame.configure(text=f"Сообщения из: {self.selected_dialog_name}")
        
        # Очищаем список сообщений
        self.messages_tree.delete(*self.messages_tree.get_children())
        
        # Загружаем сообщения для выбранного диалога
        self.load_messages()

    def update_dialogs_cache(self):
        """Обновление кеша диалогов"""
        self.progress.start()
        self.update_cache_btn.state(['disabled'])
        
        async def run():
            try:
                if not self.client_manager:
                    self.client_manager = TelegramClientManager({
                        'config_name': self.config_var.get(),
                        'app_dir': self.app_dir,
                        'debug': self.debug_var.get(),
                        'config_format': 'json',
                        'configs_in_parent_dir': False
                    })
                
                if not await self.client_manager.init_client():
                    self.log("Ошибка: клиент не инициализирован")
                    return
                
                # Получаем лимит из настроек
                dialog_limit = int(self.max_dialogs_var.get())
                
                # Применяем фильтры с force_refresh=True для обновления кеша
                filters = {
                    'search': '',
                    'sort': 'name',
                    'limit': dialog_limit,
                    'force_refresh': True  # Принудительное обновление кеша
                }
                
                self.log(f"Запуск обновления кеша диалогов с лимитом {dialog_limit}")
                await self.client_manager.filter_dialogs(filters)
                self.log("Кеш диалогов успешно обновлен")
                
                # Обновляем список диалогов
                self.load_filtered_dialogs()
            except Exception as e:
                self.log(f"Ошибка при обновлении кеша диалогов: {e}")
                import traceback
                self.log(traceback.format_exc())
            finally:
                self.progress.stop()
                self.update_cache_btn.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(run(), self.loop) 