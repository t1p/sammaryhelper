import os
import tkinter as tk
from tkinter import ttk
import time

class ToolTip:
    """Класс для создания всплывающих подсказок"""
    def __init__(self, widget, text='', delay=None):
        self.widget = widget
        self.text = text
        self.delay = delay if delay is not None else 500  # Значение по умолчанию
        self.tip_window = None
        self.id = None
        self.x = self.y = 0
        self.hovering = False
        
        # Привязываем обработчики событий
        self.widget.bind('<Enter>', self.on_enter)
        self.widget.bind('<Leave>', self.on_leave)
        self.widget.bind('<ButtonPress>', self.hide_tip)
        self.widget.bind('<Motion>', self.on_motion)

    def on_enter(self, event=None):
        """Обработчик входа курсора"""
        self.hovering = True
        self.schedule_show_tip()

    def on_leave(self, event=None):
        """Обработчик выхода курсора"""
        self.hovering = False
        self.hide_tip()
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def on_motion(self, event=None):
        """Обработчик перемещения курсора"""
        if self.tip_window and self.hovering:
            x, y, _, _ = self.widget.bbox("insert")
            x += self.widget.winfo_rootx() + 25
            y += self.widget.winfo_rooty() + 25
            self.tip_window.wm_geometry(f"+{x}+{y}")

    def schedule_show_tip(self):
        """Запланировать показ подсказки"""
        if self.id:
            self.widget.after_cancel(self.id)
        self.id = self.widget.after(self.delay, self.show_tip)

    def show_tip(self, event=None):
        """Показать подсказку"""
        if self.tip_window or not self.text or not self.hovering:
            return
            
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        # Используем системные стили
        bg = 'SystemButtonFace'
        fg = self.widget.cget('foreground') or 'SystemWindowText'
        font = self.widget.cget('font') or ('Arial', '10', 'normal')
        
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background=bg, foreground=fg,
                        relief=tk.SOLID, borderwidth=1,
                        font=font)
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        """Скрыть подсказку"""
        if self.tip_window:
            self.tip_window.destroy()
        self.tip_window = None
from tkinter import ttk, messagebox, scrolledtext
import asyncio
import threading
import datetime
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
        self.root.minsize(600, 400)  # Минимальный размер окна
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Привязываем обработчик изменения размеров окна
        self.root.bind('<Configure>', self.on_window_resize)
        
        # Настройка стиля приложения
        self.setup_styles()
        
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.loop = asyncio.new_event_loop()
        self.running = True
        self.loop_thread = None
        # Удален избыточный вызов, так как loop уже создан выше
        # self._ensure_loop_created()
        
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
            'max_messages': '100',
            'tooltip_delay': 500  # Время задержки показа подсказок (мс)
        }
        
        # Загружаем сохраненные настройки
        saved_settings = load_settings(self.app_dir)
        self.settings.update(saved_settings)
        
        self.debug_var = tk.BooleanVar(value=self.settings.get('debug', False))

        # Определяем имя последнего использованного конфига
        config_name = self.settings.get('last_config', '')

        # Загружаем настройки из выбранного файла конфига (*.py)
        # и добавляем их в self.settings перед инициализацией менеджеров
        try:
            config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
            loaded_config = load_config(config_path)
            # Добавляем ключи из конфига в settings, перезаписывая значения из sh_profile.json при совпадении
            if hasattr(loaded_config, 'api_id'): self.settings['api_id'] = loaded_config.api_id
            if hasattr(loaded_config, 'api_hash'): self.settings['api_hash'] = loaded_config.api_hash
            if hasattr(loaded_config, 'openai_api_key'): self.settings['openai_api_key'] = loaded_config.openai_api_key
            if hasattr(loaded_config, 'use_proxy'): self.settings['use_proxy'] = loaded_config.use_proxy
            if hasattr(loaded_config, 'proxy_settings'): self.settings['proxy_settings'] = loaded_config.proxy_settings
            if hasattr(loaded_config, 'db_settings'): self.settings['db_settings'] = loaded_config.db_settings
            self.log(f"Настройки из конфига '{config_name}.py' загружены и добавлены в self.settings.")
        except FileNotFoundError:
            self.log(f"Файл конфига '{config_name}.py' не найден. Использование настроек из sh_profile.json.")
        except Exception as e:
            self.log(f"Ошибка при загрузке конфига '{config_name}.py': {e}")

        # Устанавливаем состояние чекбокса "Дебаг"

        self.setup_main_tab()
        self.setup_config_tab()  # Добавляем настройку новой вкладки
        self.setup_settings_tab()

        # Инициализируем client_manager и ai_manager с обновленными настройками
        self.client_manager = TelegramClientManager({
            'config_name': config_name, # config_name все еще нужен для client_manager
            'app_dir': self.app_dir,
            'debug': self.debug_var.get(),
            # Передаем другие настройки клиента, если они есть в self.settings
            'system_version': self.settings.get('system_version'),
            'device_model': self.settings.get('device_model'),
            'app_version': self.settings.get('app_version')
        })
        # Теперь self.settings содержит API ключ из конфига (если он был найден)
        self.ai_manager = AIChatManager(self.settings)

        self.dialogs = []
        self.messages = []  # Добавляем атрибут для хранения сообщений

        # Устанавливаем значение config_var после загрузки настроек
        config_files = get_config_files(self.app_dir)
        self.config_combo['values'] = config_files
        if config_name in config_files:
             self.config_combo.set(config_name)
        elif config_files:
             self.config_combo.set(config_files[0])
             self.settings['last_config'] = config_files[0] # Обновляем last_config если выбран первый файл
             self.save_settings() # Сохраняем обновленный last_config

        self.config_combo.bind('<<ComboboxSelected>>', self.on_config_change)

        # Загружаем состояние окна
        self.load_window_state()

        # Привязываем событие закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def create_tooltip(self, widget, text):
        """Создание подсказки с учетом настроек"""
        delay = self.settings.get('tooltip_delay', 500)
        return ToolTip(widget, text, delay=delay)
        
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
    
    def on_window_resize(self, event):
        """Обработчик изменения размеров окна"""
        # Игнорируем события от дочерних виджетов
        if event.widget != self.root:
            return
            
        # Игнорируем слишком частые вызовы (дебаунсинг)
        current_time = time.time()
        if hasattr(self, 'last_resize_time') and current_time - self.last_resize_time < 0.1:
            return
        self.last_resize_time = current_time
            
        # Инициализируем начальные размеры и пропорции при первом вызове
        if not hasattr(self, 'initial_window_size'):
            self.initial_window_size = (self.root.winfo_width(), self.root.winfo_height())
            self.initial_pane_weights = {'main': [1, 1, 2], 'msg': [2, 1], 'bottom': [1, 1]}
            
        # Обновляем пропорции панелей при изменении размеров окна
        if hasattr(self, 'main_paned') and hasattr(self, 'msg_paned') and hasattr(self, 'bottom_paned'):
            self.update_pane_proportions()
            
    def update_pane_proportions(self):
        """Обновление пропорций панелей при изменении размеров окна"""
        # Получаем текущие размеры окна
        current_width = self.root.winfo_width()
        current_height = self.root.winfo_height()
        
        # Пропорционально изменяем размеры панелей
        if hasattr(self, 'initial_window_size'):
            width_ratio = current_width / self.initial_window_size[0]
            height_ratio = current_height / self.initial_window_size[0]
            
            # Обновляем размеры панелей, если они существенно изменились
            if abs(width_ratio - 1.0) > 0.1 or abs(height_ratio - 1.0) > 0.1:
                # Обновляем пропорции основной панели
                if hasattr(self, 'main_paned'):
                    try:
                        # Получаем текущие размеры панелей
                        panes = self.main_paned.panes()
                        if len(panes) == 3:  # Если у нас 3 панели
                            # Устанавливаем пропорции согласно сохраненным весам
                            weights = self.initial_pane_weights.get('main', [1, 1, 2])
                            total_width = sum(weights)
                            
                            # Устанавливаем позиции разделителей (sash) с учетом пропорций
                            available_width = current_width - 20  # Учитываем отступы
                            sash_pos1 = int(available_width * weights[0] / total_width)
                            sash_pos2 = int(available_width * (weights[0] + weights[1]) / total_width)
                            
                            # Устанавливаем позиции разделителей
                            self.main_paned.sashpos(0, sash_pos1)
                            self.main_paned.sashpos(1, sash_pos2)
                    except Exception as e:
                        self.log(f"Ошибка при обновлении пропорций основной панели: {e}")
                
                # Обновляем пропорции вертикальных панелей
                if hasattr(self, 'msg_paned'):
                    try:
                        panes = self.msg_paned.panes()
                        if len(panes) == 2:
                            weights = self.initial_pane_weights.get('msg', [2, 1])
                            total_height = sum(weights)
                            
                            available_height = current_height - 150  # Учитываем отступы и другие элементы
                            sash_pos = int(available_height * weights[0] / total_height)
                            
                            # Устанавливаем позицию разделителя
                            self.msg_paned.sashpos(0, sash_pos)
                    except Exception as e:
                        self.log(f"Ошибка при обновлении пропорций панели сообщений: {e}")
                
                # Обновляем пропорции нижней панели
                if hasattr(self, 'bottom_paned'):
                    try:
                        panes = self.bottom_paned.panes()
                        if len(panes) == 2:
                            weights = self.initial_pane_weights.get('bottom', [1, 1])
                            total_width = sum(weights)
                            
                            available_width = current_width - 20
                            sash_pos = int(available_width * weights[0] / total_width)
                            
                            # Устанавливаем позицию разделителя
                            self.bottom_paned.sashpos(0, sash_pos)
                    except Exception as e:
                        self.log(f"Ошибка при обновлении пропорций нижней панели: {e}")
                
                # Обновляем интерфейс
                self.root.update_idletasks()
                
    def setup_main_tab(self):
        """Настройка основной вкладки"""
        # Создаем основной PanedWindow для разделения интерфейса на части
        self.main_paned = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Левая панель для диалогов - используем LabelFrame вместо Frame
        self.dialogs_container = ttk.LabelFrame(self.main_paned, text="Диалоги")
        self.main_paned.add(self.dialogs_container, weight=1)
        
        # Средняя панель для тем
        self.topics_container = ttk.LabelFrame(self.main_paned, text="Темы")
        self.main_paned.add(self.topics_container, weight=1)
        
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
        
        # Добавляем информацию о множественном выборе
        self.selected_dialogs_var = tk.StringVar(value="Выбрано диалогов: 0")
        self.selected_dialogs_label = ttk.Label(self.dialogs_filter_frame, textvariable=self.selected_dialogs_var)
        self.selected_dialogs_label.grid(row=0, column=4, padx=5, pady=5, sticky=tk.E)
        
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
        
        # Добавляем обработчики нажатия кнопок
        self.load_dialogs_btn.bind("<Button-1>", lambda e: self.log("[КНОПКА] Нажата 'Загрузить диалоги'"), add="+")
        self.update_cache_btn.bind("<Button-1>", lambda e: self.log("[КНОПКА] Нажата 'Обновить кеш'"), add="+")
        
        # Список диалогов - делаем LabelFrame для выделения списка
        self.dialogs_frame = ttk.LabelFrame(self.dialogs_container, text="Список диалогов")
        self.dialogs_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.dialogs_tree = ttk.Treeview(self.dialogs_frame, columns=('name', 'type', 'folder', 'unread', 'id'), show='headings', selectmode='extended')
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
        # Добавляем дебаг вывод для выбора диалога
        self.dialogs_tree.bind('<<TreeviewSelect>>', lambda e: self.log("[СОБЫТИЕ] Выбран диалог"), add="+")
        
        # === НАСТРОЙКА СЕКЦИИ ТЕМ ===
        
        # Фрейм для списка тем с заголовком
        self.topics_frame = ttk.LabelFrame(self.topics_container, text="Список тем")
        self.topics_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Treeview для отображения тем
        self.topics_tree = ttk.Treeview(self.topics_frame, columns=('id', 'title', 'unread'), show='headings')
        self.topics_tree.heading('id', text='ID', command=lambda: self.treeview_sort_column(self.topics_tree, 'id', False))
        self.topics_tree.heading('title', text='Название', command=lambda: self.treeview_sort_column(self.topics_tree, 'title', False))
        self.topics_tree.heading('unread', text='Непрочитано', command=lambda: self.treeview_sort_column(self.topics_tree, 'unread', False))
        self.topics_tree.column('id', width=50)
        self.topics_tree.column('title', width=200)
        self.topics_tree.column('unread', width=100)
        
        scrollbar = ttk.Scrollbar(self.topics_frame, orient=tk.VERTICAL, command=self.topics_tree.yview)
        self.topics_tree.configure(yscrollcommand=scrollbar.set)
        
        self.topics_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Добавляем обработчик выбора темы
        self.topics_tree.bind('<<TreeviewSelect>>', self.on_topic_select)
        # Добавляем дебаг вывод для выбора темы
        self.topics_tree.bind('<<TreeviewSelect>>', lambda e: self.log("[СОБЫТИЕ] Выбрана тема"), add="+")
        
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
        
        # Переключатель для показа всех сообщений без учета тем
        self.show_all_messages_var = tk.BooleanVar(value=False)
        self.show_all_messages_checkbox = ttk.Checkbutton(
            self.messages_filter_frame, 
            text="Показать все сообщения", 
            variable=self.show_all_messages_var,
            command=self.toggle_show_all_messages
        )
        self.show_all_messages_checkbox.grid(row=3, column=0, columnspan=4, padx=5, pady=5, sticky=tk.W)
        
        # Добавляем обработчик для отслеживания нажатия на чекбокс
        self.show_all_messages_var.trace_add("write", lambda *args: self.log(f"[ПЕРЕКЛЮЧАТЕЛЬ] Изменено состояние 'Показать все сообщения': {self.show_all_messages_var.get()}"))
        
        # Кнопка для загрузки сообщений
        self.load_messages_btn = ttk.Button(self.messages_filter_frame, text="Сообщения", command=self.load_messages)
        self.load_messages_btn.grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        
        # Кнопка для применения фильтров к загруженным сообщениям
        self.filter_messages_btn = ttk.Button(
            self.messages_filter_frame, 
            text="Применить фильтры", 
            command=self.apply_filter_to_loaded_messages
        )
        self.filter_messages_btn.grid(row=4, column=2, columnspan=2, padx=5, pady=5, sticky=tk.E)
        
        # Добавляем обработчики нажатия кнопок
        self.load_messages_btn.bind("<Button-1>", lambda e: self.log("[КНОПКА] Нажата 'Сообщения'"), add="+")
        self.filter_messages_btn.bind("<Button-1>", lambda e: self.log("[КНОПКА] Нажата 'Применить фильтры'"), add="+")
        
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
        # Добавляем фрейм для расширенного поиска в начале интерфейса
        self.setup_search_frame()
        
        # Индикатор прогресса
        self.progress = ttk.Progressbar(self.main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, padx=5, pady=5)
        self.progress.pack(fill=tk.X, padx=5, pady=5)
    
    def setup_search_frame(self):
        """Настройка фрейма расширенного поиска"""
        # Создаем контейнер для расширенного поиска в самом начале основного интерфейса
        style = ttk.Style()
        style.configure('Search.TLabelframe', background='#e6f2ff')
        style.configure('Search.TLabelframe.Label', font=('Arial', 11, 'bold'), foreground='#0066cc', background='#e6f2ff')
        
        # Добавляем состояние свернутости в настройки
        self.settings.setdefault('search_frame_collapsed', False)
        
        # Создаем основной контейнер
        self.search_container = ttk.Frame(self.main_frame)
        self.search_container.pack(fill=tk.X, padx=5, pady=5, before=self.main_paned)
        
        # Создаем заголовок с кнопкой сворачивания
        self.search_header = ttk.Frame(self.search_container)
        self.search_header.pack(fill=tk.X)
        
        # Иконка сворачивания/разворачивания
        icon_text = "▼" if self.settings['search_frame_collapsed'] else "▲"
        self.toggle_icon = ttk.Label(self.search_header, text=icon_text, font=('Arial', 11, 'bold'), foreground='#0066cc')
        self.toggle_icon.pack(side=tk.LEFT, padx=(5, 0))
        
        # Заголовок
        self.search_title = ttk.Label(self.search_header, text="Расширенный поиск по нескольким чатам",
                                     font=('Arial', 11, 'bold'), foreground='#0066cc')
        self.search_title.pack(side=tk.LEFT, padx=5)
        
        # Привязываем обработчики клика
        self.toggle_icon.bind("<Button-1>", self.toggle_search_frame)
        self.search_title.bind("<Button-1>", self.toggle_search_frame)
        self.search_header.bind("<Button-1>", self.toggle_search_frame)
        
        # Добавляем подсказку
        self.create_tooltip(self.search_header, "Щелкните для сворачивания/разворачивания")
        
        # Создаем фрейм для содержимого
        self.search_frame = ttk.LabelFrame(self.search_container, style='Search.TLabelframe')
        self.search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Создаем внутренний фрейм для содержимого
        self.search_content_frame = ttk.Frame(self.search_frame)
        
        # Управление видимостью содержимого
        if not self.settings['search_frame_collapsed']:
            self.search_content_frame.pack(fill=tk.X, padx=5, pady=5)
        else:
            # Устанавливаем минимальную высоту для фрейма
            self.search_frame.configure(height=10)
            self.search_frame.pack_propagate(False)  # Запрещаем изменение размера
        
        # Добавляем информацию о выбранных диалогах в фрейм поиска
        selection_frame = ttk.Frame(self.search_content_frame)
        selection_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.search_selection_label = ttk.Label(selection_frame, textvariable=self.selected_dialogs_var, font=('Arial', 10, 'bold'))
        self.search_selection_label.pack(side=tk.LEFT, padx=5)
        
        # Добавляем инструкции по выбору
        instruction_frame = ttk.Frame(self.search_content_frame)
        instruction_frame.pack(fill=tk.X, padx=5, pady=2)
        
        instruction_text = "Выберите несколько диалогов, удерживая Ctrl и кликая на диалоги в списке слева"
        ttk.Label(instruction_frame, text=instruction_text, font=('Arial', 9, 'italic')).pack(anchor=tk.W)
        
        # Создаем контейнер для параметров поиска с отступами и рамкой
        style.configure('SearchParams.TFrame', background='#f0f8ff')
        search_params_frame = ttk.Frame(self.search_content_frame, style='SearchParams.TFrame')
        search_params_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Разделяем параметры на левую и правую колонки для лучшей организации
        left_frame = ttk.Frame(search_params_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        right_frame = ttk.Frame(search_params_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        # Левая колонка: Текст сообщения, отправитель и дата
        ttk.Label(left_frame, text="Текст сообщения:", font=('Arial', 9, 'bold')).grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.text_search_var = tk.StringVar()
        text_entry = ttk.Entry(left_frame, textvariable=self.text_search_var, width=25)
        text_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        text_help_label = ttk.Label(left_frame, text="Слово или фраза в сообщении", font=('Arial', 8))
        text_help_label.grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)
        self.create_tooltip(text_help_label, "Введите текст для поиска в сообщениях")
        
        ttk.Label(left_frame, text="Отправитель:", font=('Arial', 9, 'bold')).grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.sender_search_var = tk.StringVar()
        sender_entry = ttk.Entry(left_frame, textvariable=self.sender_search_var, width=25)
        sender_entry.grid(row=1, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        sender_help_label = ttk.Label(left_frame, text="Имя или часть имени отправителя", font=('Arial', 8))
        sender_help_label.grid(row=1, column=2, padx=5, pady=2, sticky=tk.W)
        self.create_tooltip(sender_help_label, "Введите имя отправителя или его часть")
        
        ttk.Label(left_frame, text="Дата:", font=('Arial', 9, 'bold')).grid(row=2, column=0, padx=5, pady=2, sticky=tk.W)
        self.date_search_var = tk.StringVar()
        date_entry = ttk.Entry(left_frame, textvariable=self.date_search_var, width=25)
        date_entry.grid(row=2, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        date_help_label = ttk.Label(left_frame, text="Формат: ГГГГ-ММ-ДД", font=('Arial', 8))
        date_help_label.grid(row=2, column=2, padx=5, pady=2, sticky=tk.W)
        self.create_tooltip(date_help_label, "Введите дату в формате ГГГГ-ММ-ДД для поиска сообщений за определенную дату")
        
        # Правая колонка: Статус ответа и кнопка поиска
        ttk.Label(right_frame, text="Статус ответа:", font=('Arial', 9, 'bold')).grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.reply_status_var = tk.StringVar(value="all")
        reply_status_values = {
            'all': 'Все сообщения',
            'replied': 'С ответами',
            'not_replied': 'Без ответов'
        }
        reply_status_combo = ttk.Combobox(right_frame, textvariable=self.reply_status_var, state="readonly", width=25)
        reply_status_combo['values'] = list(reply_status_values.keys())
        reply_status_combo.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W+tk.E)
        
        # Добавляем текстовое описание выбранного значения
        self.reply_status_description = ttk.Label(right_frame, text="Все сообщения", font=('Arial', 8))
        self.reply_status_description.grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)
        
        # Обработчик изменения статуса ответа
        def update_reply_status_description(*args):
            selected = self.reply_status_var.get()
            if selected in reply_status_values:
                self.reply_status_description.config(text=reply_status_values[selected])
        
        self.reply_status_var.trace_add("write", update_reply_status_description)
        
        # Добавляем пустую строку для выравнивания с левой колонкой
        ttk.Label(right_frame, text="").grid(row=1, column=0, padx=5, pady=2)
        
        # Кнопка поиска с улучшенным стилем
        style.configure('Search.TButton', font=('Arial', 10, 'bold'))
        self.search_btn = ttk.Button(
            self.search_content_frame,
            text="Искать во всех выбранных чатах",
            command=self.search_all_chats,
            style='Search.TButton'
        )
        self.search_btn.pack(fill=tk.X, padx=20, pady=10)
        # По умолчанию кнопка поиска недоступна
        self.search_btn.state(['disabled'])
        
    def toggle_search_frame(self, event):
        """Переключение состояния фрейма поиска (свернуть/развернуть)"""
        # Изменяем состояние
        self.settings['search_frame_collapsed'] = not self.settings['search_frame_collapsed']
        
        # Обновляем иконку
        self.toggle_icon.config(text="▼" if self.settings['search_frame_collapsed'] else "▲")
        
        # Управляем видимостью только содержимого, сам фрейм остается видимым
        if self.settings['search_frame_collapsed']:
            # Скрываем содержимое
            self.search_content_frame.pack_forget()
            
            # Устанавливаем минимальную высоту для фрейма
            self.search_frame.configure(height=10)
            self.search_frame.pack_propagate(False)  # Запрещаем изменение размера
        else:
            # Восстанавливаем нормальные размеры
            self.search_frame.pack_propagate(True)  # Разрешаем изменение размера
            
            # Показываем содержимое
            self.search_content_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Обновляем интерфейс
        self.root.update_idletasks()
        
        # Сохраняем настройки
        self.save_settings()
    
    def update_dialogs_selection_status(self):
        """Обновляет статус выбора диалогов для множественного поиска"""
        if hasattr(self, 'selected_dialogs'):
            count = len(self.selected_dialogs)
            self.selected_dialogs_var.set(f"Выбрано диалогов: {count}")
            
            # Если выбрано хотя бы один диалог, активируем кнопку мульти-поиска
            if count > 0:
                self.search_btn.state(['!disabled'])
            else:
                self.search_btn.state(['disabled'])
        else:
            self.selected_dialogs_var.set("Выбрано диалогов: 0")
            self.search_btn.state(['disabled'])
            
    def setup_config_tab(self):
        """Настройка вкладки конфига"""
        # Выбор конфига
        ttk.Label(self.config_frame, text="Выберите конфиг:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.config_var = tk.StringVar(value=self.settings.get('last_config', ''))
        self.config_combo = ttk.Combobox(self.config_frame, textvariable=self.config_var, state="readonly")
        config_files = get_config_files(self.app_dir)
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
    async def update_models_list(self):
        """Обновление списка доступных моделей OpenAI"""
        self.log("[МОДЕЛИ] Попытка обновления списка моделей...")
        try:
            self._ensure_loop_active()
            
            # Получаем полный список моделей
            all_models = await self.ai_manager.get_available_models()
            
            # Фильтруем модели, исключая специализированные
            filtered_models = []
            for model in all_models:
                # Проверяем, требует ли модель специальных возможностей
                is_specialized = False
                
                # Проверка по ID модели
                model_id = model['id']
                if ("audio" in model_id or
                    "whisper" in model_id or
                    "dall-e" in model_id or
                    "vision" in model_id):
                    is_specialized = True
                    self.log(f"[МОДЕЛИ] Исключена специализированная модель: {model_id}")
                
                # Проверка по возможностям модели
                capabilities = model.get('capabilities', {})
                if capabilities.get('requires_audio') or capabilities.get('requires_vision'):
                    is_specialized = True
                    self.log(f"[МОДЕЛИ] Исключена модель с особыми требованиями: {model_id}")
                
                # Добавляем модель, если она не специализированная
                if not is_specialized:
                    filtered_models.append(model)
            
            # Добавляем алиасы моделей для удобства
            model_aliases = [
                {"id": "gpt4-latest", "description": "Последняя версия GPT-4", "alias_for": "gpt-4o"},
                {"id": "gpt3-latest", "description": "Последняя версия GPT-3.5", "alias_for": "gpt-3.5-turbo"}
            ]
            
            # Объединяем отфильтрованные модели и алиасы
            display_models = filtered_models + model_aliases
            
            # Сохраняем полный список моделей для внутреннего использования
            self.settings['all_models'] = all_models
            
            # Сохраняем отфильтрованный список для отображения
            self.settings['available_models'] = display_models
            
            # Создаем список ID моделей для отображения в комбобоксе
            model_ids = [m['id'] for m in display_models]
            
            # Добавляем информативное сообщение в лог
            if not display_models:
                self.log("[МОДЕЛИ] Получен пустой список моделей после фильтрации.")
            
            # Обновление UI должно происходить в основном потоке Tkinter
            self.root.after(0, lambda: self.model_combo.config(values=model_ids))
            self.log(f"[МОДЕЛИ] Список моделей успешно обновлен. Найдено {len(display_models)} моделей после фильтрации.")
        except Exception as e:
            self.log(f"[МОДЕЛИ] Ошибка при обновлении моделей: {str(e)}")
            messagebox.showerror("Ошибка", f"Не удалось обновить модели: {str(e)}")

    def _update_models_handler(self):
        """Обработчик кнопки обновления моделей с использованием asyncio"""
        try:
            self.log("[МОДЕЛИ] Запуск асинхронной задачи обновления моделей...") # Add logging
            asyncio.run_coroutine_threadsafe(
                self.update_models_list(),
                self.loop
            )
        except Exception as e:
            self.log(f"[МОДЕЛИ] Ошибка при запуске асинхронной задачи обновления: {str(e)}") # Add logging in except
            messagebox.showerror("Ошибка", f"Ошибка при запуске обновления: {str(e)}")

    def on_model_select(self, event):
        """Обработчик выбора модели"""
        selected_model = self.model_var.get()
        if selected_model:
            # Проверяем, является ли выбранная модель алиасом
            model_aliases = {
                'gpt4-latest': 'gpt-4o',
                'gpt3-latest': 'gpt-3.5-turbo'
            }
            
            # Если выбран алиас, сохраняем его, но логируем реальную модель
            if selected_model in model_aliases:
                actual_model = model_aliases[selected_model]
                self.log(f"[МОДЕЛИ] Выбран алиас '{selected_model}', будет использована модель: {actual_model}")
            else:
                self.log(f"[МОДЕЛИ] Выбрана модель: {selected_model}")
            
            # Сохраняем выбранную модель в настройках
            self.settings['openai_model'] = selected_model

    def setup_settings_tab(self):
        """Настройка вкладки настроек"""
        # Выбор модели
        ttk.Label(self.settings_frame, text="Модель OpenAI:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar(value=self.settings['openai_model'])
        self.model_combo = ttk.Combobox(self.settings_frame, textvariable=self.model_var)
        
        # Получаем список ID моделей для отображения
        if 'available_models' in self.settings and isinstance(self.settings['available_models'], list):
            if all(isinstance(m, dict) for m in self.settings['available_models']):
                model_ids = [m['id'] for m in self.settings['available_models']]
                self.model_combo['values'] = model_ids
            else:
                self.model_combo['values'] = self.settings['available_models']
        
        self.model_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.model_combo.bind('<<ComboboxSelected>>', self.on_model_select)
        
        # Добавляем подсказку для комбобокса моделей
        self.create_tooltip(self.model_combo, "Выберите модель OpenAI. Алиасы 'gpt4-latest' и 'gpt3-latest' автоматически используют последние версии моделей.")
        
        # Кнопка обновления списка моделей
        self.update_models_btn = ttk.Button(
            self.settings_frame,
            text="Обновить список",
            command=self._update_models_handler
        )
        self.update_models_btn.grid(row=0, column=2, padx=5, pady=5)
        
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
        client_version_label = ttk.Label(self.settings_frame, text="Версия клиента:", font=('', 10, 'bold'))
        client_version_label.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(10,5))
        self.create_tooltip(client_version_label, "Настройки версии клиента Telegram для эмуляции")
        
        # System Version
        ttk.Label(self.settings_frame, text="Версия системы:").grid(row=6, column=0, sticky=tk.W)
        self.system_version_var = tk.StringVar(value=self.settings.get('system_version', 'Windows 10'))
        self.system_version_combo = ttk.Combobox(self.settings_frame, textvariable=self.system_version_var)
        self.create_tooltip(self.system_version_combo, "Версия операционной системы для эмуляции")
        self.system_version_combo['values'] = self.settings.get('system_versions', ['Windows 10', 'Android 13.0', 'iOS 16.5', 'macOS 13.4'])
        self.system_version_combo.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=5)
        
        # Device Model
        ttk.Label(self.settings_frame, text="Модель устройства:").grid(row=7, column=0, sticky=tk.W)
        self.device_model_var = tk.StringVar(value=self.settings.get('device_model', 'Desktop'))
        self.device_model_combo = ttk.Combobox(self.settings_frame, textvariable=self.device_model_var)
        self.create_tooltip(self.device_model_combo, "Модель устройства для эмуляции")
        self.device_model_combo['values'] = self.settings.get('device_models', ['Desktop', 'Samsung Galaxy S23', 'iPhone 14 Pro', 'MacBook Pro'])
        self.device_model_combo.grid(row=7, column=1, sticky=(tk.W, tk.E), padx=5)
        
        # App Version
        ttk.Label(self.settings_frame, text="Версия приложения:").grid(row=8, column=0, sticky=tk.W)
        self.app_version_var = tk.StringVar(value=self.settings.get('app_version', '4.8.1'))
        self.app_version_combo = ttk.Combobox(self.settings_frame, textvariable=self.app_version_var)
        self.create_tooltip(self.app_version_combo, "Версия приложения Telegram для эмуляции")
        self.app_version_combo['values'] = self.settings.get('app_versions', ['4.8.1', '9.6.3', '9.7.0'])
        self.app_version_combo.grid(row=8, column=1, sticky=(tk.W, tk.E), padx=5)
        
        # Кнопка применения версии клиента
        self.apply_version_btn = ttk.Button(self.settings_frame, text="Применить версию",
                                          command=self.apply_client_version)
        self.create_tooltip(self.apply_version_btn, "Применить выбранные настройки версии клиента")
        self.apply_version_btn.grid(row=9, column=0, columnspan=2, pady=10)
        
        # Кнопка сохранения настроек
        self.save_settings_btn = ttk.Button(self.settings_frame, text="Сохранить настройки", command=self.save_settings)
        self.create_tooltip(self.save_settings_btn, "Сохранить все настройки приложения")
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
            settings_path = os.path.join(self.app_dir, 'configs', 'sh_profile.json')
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

    def _ensure_loop_created(self):
        """Проверяет, создан ли event loop, и создает его при необходимости"""
        if not hasattr(self, 'loop') or self.loop is None or self.loop.is_closed():
            self.loop = asyncio.new_event_loop()
            self.log("Создан новый event loop")

    def _ensure_loop_active(self):
        """Проверяет, активен ли event loop"""
        if not hasattr(self, 'loop') or self.loop is None or self.loop.is_closed():
            self.log("[ОШИБКА] Event loop не активен при попытке выполнения асинхронной задачи.") # Add logging
            raise RuntimeError("Event loop не активен")

    def run(self):
        """Запуск приложения"""
        self._ensure_loop_created()
        
        def run_loop():
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_forever()
            except Exception as e:
                self.log(f"Ошибка в event loop: {e}")
            finally:
                if not self.loop.is_closed():
                    self.loop.close()

        self.loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
        
        try:
            self.root.mainloop()
        finally:
            self.cleanup()
            if hasattr(self, 'loop_thread') and self.loop_thread.is_alive():
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

                # Загружаем настройки из нового файла конфига (*.py)
                # и обновляем self.settings перед инициализацией менеджеров
                try:
                    config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
                    loaded_config = load_config(config_path)
                    # Обновляем self.settings с новыми значениями из конфига
                    if hasattr(loaded_config, 'api_id'): self.settings['api_id'] = loaded_config.api_id
                    if hasattr(loaded_config, 'api_hash'): self.settings['api_hash'] = loaded_config.api_hash
                    if hasattr(loaded_config, 'openai_api_key'): self.settings['openai_api_key'] = loaded_config.openai_api_key
                    if hasattr(loaded_config, 'use_proxy'): self.settings['use_proxy'] = loaded_config.use_proxy
                    if hasattr(loaded_config, 'proxy_settings'): self.settings['proxy_settings'] = loaded_config.proxy_settings
                    if hasattr(loaded_config, 'db_settings'): self.settings['db_settings'] = loaded_config.db_settings
                    self.log(f"Настройки из нового конфига '{config_name}.py' загружены и обновлены в self.settings.")
                except FileNotFoundError:
                    self.log(f"Файл конфига '{config_name}.py' не найден. Использование текущих настроек из sh_profile.json.")
                except Exception as e:
                    self.log(f"Ошибка при загрузке нового конфига '{config_name}.py': {e}")

                # Создаем новый клиент и AI менеджер с обновленными настройками
                self.client_manager = TelegramClientManager({
                    'config_name': config_name,
                    'app_dir': self.app_dir,
                    'debug': self.debug_var.get(),
                    # Передаем другие настройки клиента, если они есть в self.settings
                    'system_version': self.settings.get('system_version'),
                    'device_model': self.settings.get('device_model'),
                    'app_version': self.settings.get('app_version')
                })
                # Инициализируем ai_manager с обновленными настройками
                self.ai_manager = AIChatManager(self.settings)

                # Очищаем список диалогов
                self.dialogs = []
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                self.log(f"Выбран конфиг: {config_name}. Клиент и AI менеджер переинициализированы.")

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

    def _handle_async_result(self, future):
        """Обрабатывает результат асинхронной операции"""
        try:
            future.result()
        except Exception as e:
            self.log(f"Ошибка в асинхронной задаче: {e}")
            messagebox.showerror("Ошибка", f"Ошибка при выполнении задачи: {e}")

    def cleanup(self):
        """Очистка ресурсов при закрытии приложения"""
        self.running = False
        
        async def cleanup_async():
            try:
                if hasattr(self, 'client_manager') and self.client_manager is not None:
                    if hasattr(self.client_manager, 'client') and self.client_manager.client is not None:
                        if self.client_manager.client.is_connected():
                            await self.client_manager.client.disconnect()
            except Exception as e:
                self.log(f"Ошибка при отключении клиента: {e}")
            finally:
                if not self.loop.is_closed():
                    self.loop.call_soon_threadsafe(self.loop.stop)
        
        try:
            if hasattr(self, 'loop') and self.loop is not None and self.loop.is_running():
                future = asyncio.run_coroutine_threadsafe(cleanup_async(), self.loop)
                future.result(timeout=5)
        except Exception as e:
            self.log(f"Ошибка при очистке ресурсов: {e}")
        finally:
            if hasattr(self, 'loop') and not self.loop.is_closed():
                self.loop.close()

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
                if self.debug_var.get():
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
                if self.dialog_search_var.get().strip():
                    search_text = self.dialog_search_var.get().lower()
                    original_count = len(self.dialogs)
                    self.dialogs = [dialog for dialog in self.dialogs if search_text in dialog['name'].lower()]
                    self.log(f"После локальной фильтрации по '{search_text}': {len(self.dialogs)} из {original_count}")
                
                self.dialogs_tree.delete(*self.dialogs_tree.get_children())
                
                for dialog in self.dialogs:
                    folder_name = f"Папка {dialog['folder_id']}" if dialog.get('folder_id') is not None else "Без папки"
                    unread_count = dialog.get('unread_count', 0)
                    
                    # Выводим отладочную информацию
                    if self.debug_var.get():
                        self.log(f"Добавление диалога: {dialog['name']}, ID: {dialog['id']}")
                    
                    self.dialogs_tree.insert('', 'end', values=(
                        dialog['name'], 
                        dialog['type'], 
                        folder_name, 
                        unread_count,
                        dialog['id']  # Важно: ID должен быть последним элементом
                    ))
                
                if self.debug_var.get():
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
            folder_name = f"Папка {dialog['folder_id']}" if dialog.get('folder_id') is not None else "Без папки"
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
            
            # Загружаем настройки базы данных
            if hasattr(config, 'db_settings'):
                db_settings = config.db_settings
                self.db_host_var.set(db_settings.get('host', 'localhost'))
                self.db_port_var.set(str(db_settings.get('port', 5432)))
                self.db_name_var.set(db_settings.get('database', 'telegram_summarizer'))
                self.db_user_var.set(db_settings.get('user', 'postgres'))
                self.db_password_var.set(db_settings.get('password', 'postgres'))
            
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

# Настройки базы данных
db_settings = {{
    "host": "{self.db_host_var.get()}",
    "port": {self.db_port_var.get() or 5432},
    "database": "{self.db_name_var.get()}",
    "user": "{self.db_user_var.get()}",
    "password": "{self.db_password_var.get()}"
}}
"""
            
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            self.log(f"Конфиг {config_name} успешно сохранен")
            
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
                # Проверяем, что client_manager существует и не равен None
                if not self.client_manager:
                    # Если client_manager не существует или равен None, создаем его
                    self.client_manager = TelegramClientManager({
                        'config_name': self.config_var.get(),
                        'app_dir': self.app_dir,
                        'debug': self.debug_var.get(),
                        'system_version': self.settings.get('system_version'),
                        'device_model': self.settings.get('device_model'),
                        'app_version': self.settings.get('app_version')
                    })
                    self.log("Создан новый экземпляр TelegramClientManager в process_ai_request")
                    
                # Проверяем, что клиент инициализирован
                if not hasattr(self.client_manager, 'client') or self.client_manager.client is None or not self.client_manager.client.is_connected():
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
                    config_path = os.path.join(self.app_dir, "configs", f"{config_name}.py")
                    config = load_config(config_path)
                    self.settings['openai_api_key'] = config.openai_api_key
                
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
        
        self.log(f"[СООБЩЕНИЯ] Загрузка сообщений для диалога ID: {self.selected_dialog_id}")
        
        self.progress.start()
        self.load_messages_btn.state(['disabled'])
        
        async def run():
            try:
                # Проверяем режим отображения всех сообщений
                show_all = self.show_all_messages_var.get()
                
                # Если выбрана тема и не включен режим "показать все", используем загрузку сообщений для темы
                if hasattr(self, 'selected_topic_id') and self.selected_topic_id is not None and not show_all:
                    self.log(f"[СООБЩЕНИЯ] Используем выбранную тему {self.selected_topic_id} для загрузки сообщений")
                    # Вызываем метод загрузки сообщений для темы
                    await self.load_topic_messages_async()
                else:
                    # Иначе загружаем все сообщения
                    if show_all:
                        self.log("[СООБЩЕНИЯ] Режим показа всех сообщений активен, игнорируем выбранную тему")
                    else:
                        self.log("[СООБЩЕНИЯ] Тема не выбрана, загружаем обычные сообщения")
                    await self.load_messages_async()
            finally:
                self.progress.stop()
                self.load_messages_btn.state(['!disabled'])
                self.log("[СООБЩЕНИЯ] Загрузка сообщений завершена")
        
        try:
            self._ensure_loop_active()
            future = asyncio.run_coroutine_threadsafe(run(), self.loop)
            future.add_done_callback(self._handle_async_result)
        except RuntimeError as e:
            self.log(f"Ошибка при запуске асинхронной задачи: {e}")
            messagebox.showerror("Ошибка", f"Не удалось запустить задачу: {e}")
    
    async def load_topic_messages_async(self):
        """Асинхронная загрузка сообщений для выбранной темы"""
        try:
            # Проверяем, что клиент инициализирован
            if not self.client_manager or not hasattr(self.client_manager, 'client') or not self.client_manager.client.is_connected():
                if not await self.client_manager.init_client():
                    self.log("Ошибка: клиент не инициализирован")
                    return
            
            # Получаем ID аккаунта
            me = await self.client_manager.client.get_me()
            account_id = str(me.phone) if me.phone else str(me.id)
            
            # Проверяем кеш, если клиент использует кеширование
            use_cache = self.client_manager.use_cache and self.client_manager.db_handler
            
            # Получаем фильтры от пользователя и добавляем ID темы
            limit = int(self.max_messages_var.get())
            self.log(f"[ТЕМА_СООБЩЕНИЯ] Запрошен лимит: {limit} сообщений")
            
            filters = {
                'search': self.message_search_var.get(),
                'limit': limit,
                'filter': self.message_filter_var.get(),
                'topic_id': self.selected_topic_id
            }
            
            # Логируем запрос для отладки
            self.log(f"[ТЕМА_СООБЩЕНИЯ] Загрузка сообщений для темы {self.selected_topic_id} в диалоге {self.selected_dialog_id} с фильтрами: {filters}")
            
            # Загружаем сообщения
            messages = await self.client_manager.filter_messages(self.selected_dialog_id, filters)
            
            # Очищаем список сообщений
            self.messages_tree.delete(*self.messages_tree.get_children())
            
            # Заполняем список сообщений
            for i, message in enumerate(messages):
                # Проверяем тип поля date и форматируем соответственно
                if isinstance(message['date'], str):
                    date_str = message['date']
                else:
                    date_str = message['date'].strftime('%Y-%m-%d %H:%M:%S')
                
                # Добавляем в Treeview
                item_id = self.messages_tree.insert('', 'end', values=(
                    message['id'],
                    message['sender_name'],
                    message['text'][:100] + ('...' if len(message['text']) > 100 else ''),
                    date_str
                ))
                
                # Логируем добавление для последних 2 сообщений
                if i >= len(messages) - 2:
                    self.log(f"[ТЕМА_СООБЩЕНИЯ] Добавлено в Treeview сообщение #{i+1}: id={message['id']}, item_id={item_id}")
            
            # Сохраняем сообщения для последующей фильтрации
            self.messages = messages
            
            self.log(f"[ТЕМА_СООБЩЕНИЯ] Всего загружено сообщений темы: {len(messages)}")
            self.log(f"[ТЕМА_СООБЩЕНИЯ] Количество отображаемых сообщений: {len(self.messages_tree.get_children())}")
            
            # Отображаем последнее сообщение (прокручиваем список вниз)
            if self.messages_tree.get_children():
                last_item = self.messages_tree.get_children()[-1]
                self.messages_tree.see(last_item)
                self.log(f"[ТЕМА_СООБЩЕНИЯ] Прокручиваем к последнему сообщению ID: {self.messages_tree.item(last_item, 'values')[0]}")
            
        except Exception as e:
            self.log(f"Ошибка при загрузке сообщений темы: {e}")
            import traceback
            self.log(traceback.format_exc())
    
    def load_topic_messages(self):
        """Загрузка сообщений для выбранной темы"""
        if not hasattr(self, 'selected_dialog_id') or self.selected_dialog_id is None:
            self.log("Ошибка: не выбран диалог")
            return
            
        if not hasattr(self, 'selected_topic_id') or self.selected_topic_id is None:
            self.log("Ошибка: не выбрана тема")
            return
        
        # Проверяем режим отображения всех сообщений
        show_all = self.show_all_messages_var.get()
        if show_all:
            self.log(f"[ТЕМА_СООБЩЕНИЯ] Режим показа всех сообщений активен. Загружаем все сообщения вместо темы.")
            self.load_messages()
        
        # Получаем выбранную тему из дерева
        selected_items = self.topics_tree.selection()
        if selected_items:
            item = selected_items[0]
            topic_values = self.topics_tree.item(item, 'values')
            topic_title = topic_values[1]  # Название темы
            
            # Обновляем заголовок фрейма сообщений
            self.messages_frame.configure(text=f"Сообщения из темы: {topic_title}")
            self.log(f"[ТЕМА_СООБЩЕНИЯ] Обновлен заголовок: Сообщения из темы: {topic_title}")
        
        self.progress.start()
        self.load_messages_btn.state(['disabled'])
        
        async def run():
            try:
                self.log(f"[ТЕМА_СООБЩЕНИЯ] Начинаем загрузку сообщений темы {self.selected_topic_id}")
                await self.load_topic_messages_async()
            finally:
                self.progress.stop()
                self.load_messages_btn.state(['!disabled'])
                self.log(f"[ТЕМА_СООБЩЕНИЯ] Завершена загрузка сообщений темы {self.selected_topic_id}")
        
        asyncio.run_coroutine_threadsafe(run(), self.loop)

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
                        'debug': self.debug_var.get()
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

    async def load_messages_async(self):
        """Асинхронная загрузка сообщений для выбранного диалога"""
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
                    date_str = message['date']
                else:
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
            settings_path = os.path.join(self.app_dir, 'configs', 'sh_profile.json')
            self.log(f"Попытка загрузки состояния окна из {settings_path}")
            
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                state = settings.get('window_state', {})
                if 'geometry' in state:
                    self.root.geometry(state['geometry'])
                    self.log(f"Состояние окна загружено: {state}")
                    
                    # Загружаем пропорции панелей, если они сохранены
                    if 'pane_weights' in state:
                        self.initial_pane_weights = state['pane_weights']
                        self.log(f"Загружены пропорции панелей: {self.initial_pane_weights}")
                else:
                    self.log("Состояние окна не найдено, используются значения по умолчанию.")
                self.root.update_idletasks()
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            self.log(f"Ошибка при загрузке состояния окна: {e}")

    def save_window_state(self):
        """Сохранение состояния окна"""
        try:
            settings_path = os.path.join(self.app_dir, 'configs', 'sh_profile.json')
            self.log(f"Попытка сохранения состояния окна в {settings_path}")
            
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                settings = {}
                self.log("Создание нового файла настроек.")
            
            geometry = self.root.geometry()
            self.log(f"Текущая геометрия окна: {geometry}")
            
            # Сохраняем текущие пропорции панелей
            pane_weights = {}
            if hasattr(self, 'initial_pane_weights'):
                pane_weights = self.initial_pane_weights
            
            settings['window_state'] = {
                'geometry': geometry,
                'pane_weights': pane_weights
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
        
        # Корректно завершаем event loop
        if hasattr(self, 'loop') and self.loop and not self.loop.is_closed():
            try:
                self.log("Завершение event loop")
                self.loop.call_soon_threadsafe(self.loop.stop)
                if hasattr(self, 'loop_thread') and self.loop_thread:
                    self.loop_thread.join(timeout=1.0)
                self.loop.close()
            except Exception as e:
                self.log(f"Ошибка при завершении loop: {str(e)}")
        
        self.root.destroy()
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
        """Обработка выбора диалога"""
        selected_items = self.dialogs_tree.selection()
        if not selected_items:
            return
        
        # Обработка множественного выбора диалогов
        self.selected_dialogs = []
        for item in selected_items:
            dialog_values = self.dialogs_tree.item(item, 'values')
            dialog_id = int(dialog_values[-1])
            dialog_name = dialog_values[0]
            self.selected_dialogs.append({
                'id': dialog_id,
                'name': dialog_name
            })
        
        self.log(f"Выбрано диалогов: {len(self.selected_dialogs)}")
        
        # Обновляем статус выбора для расширенного поиска
        self.update_dialogs_selection_status()
        
        # Если выбран только один диалог, обрабатываем его как раньше для отображения тем и сообщений
        if len(selected_items) == 1:
            item = selected_items[0]
            dialog_values = self.dialogs_tree.item(item, 'values')
            selected_dialog_id = dialog_values[-1]
            selected_dialog_name = dialog_values[0]
            
            try:
                # Преобразуем ID в число
                self.selected_dialog_id = int(selected_dialog_id)
                self.selected_dialog_name = selected_dialog_name
                self.log(f"[ДИАЛОГ] Выбран диалог с ID: {self.selected_dialog_id} ({selected_dialog_name})")
                
                # Сбрасываем выбранную тему при выборе нового диалога
                if hasattr(self, 'selected_topic_id'):
                    self.log(f"[ДИАЛОГ] Сброс выбранной темы (была: {self.selected_topic_id})")
                    self.selected_topic_id = None
                    
                # Сбрасываем режим "показать все сообщения"
                if self.show_all_messages_var.get():
                    self.log(f"[ДИАЛОГ] Сброс режима 'показать все сообщения'")
                    self.show_all_messages_var.set(False)
                
                # Обновляем заголовки для лучшей визуализации контекста
                self.messages_filter_frame.configure(text=f"Фильтры сообщений: {selected_dialog_name}")
                self.messages_frame.configure(text=f"Сообщения из: {selected_dialog_name}")
                self.topics_frame.configure(text=f"Темы в: {selected_dialog_name}")
                
                # Обновляем UI
                self.load_messages_btn.state(['!disabled'])
                
                # Очищаем список сообщений при выборе нового диалога
                self.messages_tree.delete(*self.messages_tree.get_children())
                
                # Очищаем список тем и проверяем, поддерживает ли чат темы
                self.topics_tree.delete(*self.topics_tree.get_children())
                
                # Запускаем проверку наличия тем
                self.check_topics_support()
                
            except (ValueError, IndexError) as e:
                self.log(f"Ошибка при выборе диалога: {e}")
                messagebox.showerror("Ошибка", f"Не удалось выбрать диалог: {e}")
                self.selected_dialog_id = None
                self.load_messages_btn.state(['disabled'])
        else:
            # При множественном выборе очищаем темы и сообщения
            self.topics_tree.delete(*self.topics_tree.get_children())
            self.messages_tree.delete(*self.messages_tree.get_children())
            self.messages_filter_frame.configure(text=f"Фильтры сообщений: {len(selected_items)} чатов выбрано")
            self.messages_frame.configure(text=f"Сообщения из нескольких чатов")
            self.topics_frame.configure(text=f"Темы недоступны при выборе нескольких чатов")
    
    def search_all_chats(self):
        """Поиск сообщений во всех выбранных чатах"""
        if not hasattr(self, 'selected_dialogs') or not self.selected_dialogs:
            messagebox.showwarning("Предупреждение", "Выберите хотя бы один диалог для поиска")
            return
        
        # Активируем индикатор загрузки
        self.progress.start()
        self.search_btn.state(['disabled'])
        
        # Подробный дебаг о клике по кнопке поиска
        self.log("[ПОИСК] Нажата кнопка поиска по нескольким чатам")
        
        # Проверяем заполненность полей поиска
        text_value = self.text_search_var.get().strip()
        sender_value = self.sender_search_var.get().strip()
        date_value = self.date_search_var.get().strip()
        reply_status = self.reply_status_var.get()
        
        # Логирование для отладки пустых полей
        self.log(f"[ПОИСК] Проверка введенных данных:")
        self.log(f"[ПОИСК] - Текст: '{text_value}' (заполнено: {bool(text_value)})")
        self.log(f"[ПОИСК] - Отправитель: '{sender_value}' (заполнено: {bool(sender_value)})")
        self.log(f"[ПОИСК] - Дата: '{date_value}' (заполнено: {bool(date_value)})")
        self.log(f"[ПОИСК] - Статус ответа: '{reply_status}' (не 'all': {reply_status != 'all'})")
        
        if not (text_value or sender_value or date_value or reply_status != 'all'):
            self.log("[ПОИСК] Предупреждение: все критерии поиска пустые")
            choice = messagebox.askyesno(
                "Подтверждение поиска",
                "Вы не указали ни одного критерия поиска. Будут показаны все сообщения в выбранных чатах. Продолжить?"
            )
            if not choice:
                self.progress.stop()
                self.search_btn.state(['!disabled'])
                self.log("[ПОИСК] Поиск отменен пользователем")
                return
        
        # Параметры поиска
        search_params = {
            'text': text_value,
            'sender': sender_value,
            'date': date_value,
            'reply_status': reply_status,
            'limit': int(self.max_messages_var.get())
        }
        
        # Вывод информации о параметрах поиска
        self.log(f"[ПОИСК] Параметры поиска:")
        for key, value in search_params.items():
            if key != 'limit':  # не показываем лимит в каждой строке
                self.log(f"[ПОИСК] - {key}: '{value}'")
        self.log(f"[ПОИСК] - Лимит сообщений: {search_params['limit']}")
        
        # Список ID выбранных диалогов
        dialog_ids = [dialog['id'] for dialog in self.selected_dialogs]
        dialog_names = [dialog['name'] for dialog in self.selected_dialogs]
        
        self.log(f"[ПОИСК] Выбрано диалогов: {len(dialog_ids)}")
        for i, (did, name) in enumerate(zip(dialog_ids, dialog_names)):
            self.log(f"[ПОИСК] {i+1}. {name} (ID: {did})")
        
        # Обновляем заголовки для отображения процесса поиска
        self.messages_frame.configure(text=f"Поиск в {len(dialog_ids)} чатах...")
        self.topics_frame.configure(text=f"Процесс поиска...")
        
        # Визуальное отображение поиска в интерфейсе
        self.ai_chat.config(state=tk.NORMAL)
        self.ai_chat.insert(tk.END, f"Выполняется поиск по {len(dialog_ids)} выбранным чатам...\n")
        self.ai_chat.insert(tk.END, f"Критерии поиска:\n")
        if text_value:
            self.ai_chat.insert(tk.END, f"- Текст: '{text_value}'\n")
        if sender_value:
            self.ai_chat.insert(tk.END, f"- Отправитель: '{sender_value}'\n")
        if date_value:
            self.ai_chat.insert(tk.END, f"- Дата: '{date_value}'\n")
        if reply_status != 'all':
            self.ai_chat.insert(tk.END, f"- Статус ответа: '{reply_status}'\n")
        self.ai_chat.insert(tk.END, f"\nПожалуйста, подождите...\n")
        self.ai_chat.see(tk.END)
        self.ai_chat.config(state=tk.DISABLED)
        
        # Запускаем асинхронный поиск
        self.log("[ПОИСК] Запуск асинхронного поиска...")
        asyncio.run_coroutine_threadsafe(self.search_messages_async(dialog_ids, search_params), self.loop)
    
    async def search_messages_async(self, dialog_ids, search_params):
        """Асинхронный поиск сообщений в нескольких чатах"""
        search_start_time = datetime.datetime.now()
        try:
            self.log("[ПОИСК] Начало асинхронного поиска сообщений...")
            
            # Проверяем состояние клиента
            if not self.client_manager or not self.client_manager.client.is_connected():
                self.log("[ПОИСК] Клиент не подключен, инициализация...")
                if not await self.client_manager.init_client():
                    self.log("[ПОИСК] ОШИБКА: Не удалось инициализировать клиент")
                    messagebox.showerror("Ошибка", "Не удалось установить соединение с Telegram")
                    return
                else:
                    self.log("[ПОИСК] Клиент успешно инициализирован")
            else:
                self.log("[ПОИСК] Клиент уже подключен, продолжаем...")
            
            # Очищаем существующие результаты
            self.topics_tree.delete(*self.topics_tree.get_children())
            self.messages_tree.delete(*self.messages_tree.get_children())
            
            # Логируем начало поиска
            self.log(f"[ПОИСК] Вызов метода search_multiple_chats для {len(dialog_ids)} диалогов...")
            self.log(f"[ПОИСК] Параметры поиска: текст='{search_params.get('text', '')}', отправитель='{search_params.get('sender', '')}', дата='{search_params.get('date', '')}'")
            
            # Обновляем интерфейс с сообщением о начале поиска
            def update_ui_start():
                self.ai_chat.config(state=tk.NORMAL)
                self.ai_chat.insert(tk.END, f"Начало поиска: {datetime.datetime.now().strftime('%H:%M:%S')}\n")
                self.ai_chat.see(tk.END)
                self.ai_chat.config(state=tk.DISABLED)
            
            self.root.after(0, update_ui_start)
            
            # Вызываем метод поиска в нескольких чатах
            results = {}
            text_value = search_params.get('text', '').lower()
            sender_value = search_params.get('sender', '').lower()
            date_value = search_params.get('date', '')
            reply_status = search_params.get('reply_status', 'all')
            for did in dialog_ids:
                messages = await self.client_manager.filter_messages(did, search_params)
                filtered = []
                for m in messages:
                    # Фильтрация по тексту
                    if text_value and text_value not in m['text'].lower():
                        continue
                    # Фильтрация по отправителю
                    sender_field = m.get('sender_name') or m.get('sender') or ''
                    if sender_value and sender_value not in sender_field.lower():
                        continue
                    # Фильтрация по дате (ожидается формат ГГГГ-ММ-ДД)
                    if date_value:
                        m_date = m['date'] if isinstance(m['date'], str) else m['date'].strftime('%Y-%m-%d')
                        if date_value not in m_date:
                            continue
                    # Фильтрация по статусу ответа, если требуется
                    if reply_status != 'all':
                        if reply_status == 'replied' and not m.get('replied', False):
                            continue
                        if reply_status == 'not_replied' and m.get('replied', False):
                            continue
                    filtered.append(m)
                results[did] = filtered
            self.log(f"[ПОИСК] Получены результаты поиска для {len(results)} диалогов после локальной фильтрации")
            
            # Выводим отчет о результатах
            total_results = sum(len(chat_results) for chat_results in results.values())
            self.log(f"[ПОИСК] Поиск завершен. Всего найдено: {total_results} сообщений")
            
            # Подробная информация по каждому чату
            chats_with_results = 0
            for dialog_id, messages in results.items():
                dialog_name = "Неизвестный чат"
                for dialog in self.dialogs:
                    if dialog['id'] == dialog_id:
                        dialog_name = dialog['name']
                        break
                
                if len(messages) > 0:
                    chats_with_results += 1
                    
                self.log(f"[ПОИСК] Чат '{dialog_name}' (ID: {dialog_id}): найдено {len(messages)} сообщений")
            
            # Если нет результатов
            if not results or total_results == 0:
                self.log("[ПОИСК] Поиск не дал результатов")
                
                # Обновляем интерфейс с сообщением о результатах
                def update_ui_no_results():
                    self.ai_chat.config(state=tk.NORMAL)
                    self.ai_chat.insert(tk.END, "\n🔍 Поиск завершен\n")
                    self.ai_chat.insert(tk.END, "❌ По вашему запросу ничего не найдено\n")
                    search_time = datetime.datetime.now() - search_start_time
                    self.ai_chat.insert(tk.END, f"⏱️ Время поиска: {search_time.total_seconds():.2f} сек.\n")
                    self.ai_chat.see(tk.END)
                    self.ai_chat.config(state=tk.DISABLED)
                    
                    self.messages_frame.configure(text="Список сообщений: нет результатов")
                    self.topics_frame.configure(text="Результаты поиска: ничего не найдено")
                
                self.root.after(0, update_ui_no_results)
                messagebox.showinfo("Информация", "По вашему запросу ничего не найдено")
                return
            
            # Обрабатываем и отображаем результаты
            self.log("[ПОИСК] Обработка результатов поиска...")
            self.process_search_results(results)
            self.log("[ПОИСК] Результаты успешно обработаны и отображены")
            
            # Обновляем интерфейс с сообщением о результатах
            search_time = datetime.datetime.now() - search_start_time
            
            def update_ui_results():
                self.ai_chat.config(state=tk.NORMAL)
                self.ai_chat.insert(tk.END, "\n🔍 Поиск завершен\n")
                self.ai_chat.insert(tk.END, f"✅ Найдено {total_results} сообщений в {chats_with_results} чатах\n")
                self.ai_chat.insert(tk.END, f"⏱️ Время поиска: {search_time.total_seconds():.2f} сек.\n")
                self.ai_chat.see(tk.END)
                self.ai_chat.config(state=tk.DISABLED)
            
            self.root.after(0, update_ui_results)
            
        except Exception as e:
            self.log(f"[ПОИСК] ОШИБКА при поиске сообщений: {e}")
            import traceback
            self.log(traceback.format_exc())
            
            # Обновляем интерфейс с сообщением об ошибке
            def update_ui_error():
                self.ai_chat.config(state=tk.NORMAL)
                self.ai_chat.insert(tk.END, "\n❌ Ошибка при поиске\n")
                self.ai_chat.insert(tk.END, f"Текст ошибки: {str(e)}\n")
                self.ai_chat.see(tk.END)
                self.ai_chat.config(state=tk.DISABLED)
                
                self.messages_frame.configure(text="Список сообщений")
                self.topics_frame.configure(text="Произошла ошибка при поиске")
            
            self.root.after(0, update_ui_error)
            messagebox.showerror("Ошибка", f"Ошибка при поиске: {e}")
        finally:
            self.progress.stop()
            self.search_btn.state(['!disabled'])
            self.log("[ПОИСК] Поиск завершен")
    
    def process_search_results(self, results):
        """Обработка и отображение результатов поиска"""
        self.log("[РЕЗУЛЬТАТЫ] Начало обработки результатов поиска")
        
        # Очистка текущих данных в списках
        self.topics_tree.delete(*self.topics_tree.get_children())
        self.messages_tree.delete(*self.messages_tree.get_children())
        
        # Подготовка объединенного списка тем для отображения
        topics = []
        topic_id_counter = 1
        
        # Счетчик для статистики
        total_chats = 0
        total_messages = 0
        
        for dialog_id, messages in results.items():
            # Пропускаем пустые результаты
            if not messages:
                self.log(f"[РЕЗУЛЬТАТЫ] Чат {dialog_id} не содержит подходящих сообщений, пропускаем")
                continue
                
            total_chats += 1
            total_messages += len(messages)
            
            # Находим информацию о диалоге
            dialog_name = None
            dialog_type = None
            for dialog in self.dialogs:
                if dialog['id'] == dialog_id:
                    dialog_name = dialog['name']
                    dialog_type = dialog.get('type', 'Неизвестный тип')
                    break
                    
            if not dialog_name:
                dialog_name = f"Чат ID: {dialog_id}"
            
            self.log(f"[РЕЗУЛЬТАТЫ] Обработка чата '{dialog_name}' ({dialog_type}) - {len(messages)} сообщений")
            
            # Создаем "тему" для каждого чата с результатами
            topic_title = f"Результаты в {dialog_name} ({len(messages)} сообщений)"
            topics.append({
                'id': topic_id_counter,
                'title': topic_title,
                'dialog_id': dialog_id,
                'messages': messages
            })
            self.log(f"[РЕЗУЛЬТАТЫ] Создана тема #{topic_id_counter}: '{topic_title}'")
            topic_id_counter += 1
        
        # Если есть результаты, отображаем их
        if topics:
            self.log(f"[РЕЗУЛЬТАТЫ] Отображение {len(topics)} тем в дереве результатов")
            # Отображение тем в списке тем
            for topic in topics:
                item_id = self.topics_tree.insert('', 'end', values=(
                    topic['id'],
                    topic['title'],
                    len(topic['messages'])
                ))
                self.log(f"[РЕЗУЛЬТАТЫ] Добавлена тема в UI: {topic['title']} (item_id: {item_id})")
            
            # Обновляем статус
            self.log(f"[РЕЗУЛЬТАТЫ] Найдено всего {total_messages} сообщений в {total_chats} чатах")
            
            # Настраиваем заголовок для панели тем
            self.topics_frame.configure(text=f"Результаты поиска: найдено {total_messages} сообщений в {total_chats} чатах")
            
            # Настраиваем заголовок для панели сообщений
            self.messages_frame.configure(text="Выберите результат поиска для просмотра сообщений")
        else:
            self.log("[РЕЗУЛЬТАТЫ] Не найдено ни одного сообщения, удовлетворяющего критериям поиска")
            self.topics_frame.configure(text="Результаты поиска: ничего не найдено")
            self.messages_frame.configure(text="Сообщения")
        
        # Сохраняем результаты поиска для последующего отображения
        self.search_results_topics = topics
        self.log("[РЕЗУЛЬТАТЫ] Завершена обработка результатов поиска")
    
    def display_search_results_messages(self, messages):
        """Отображение сообщений из результатов поиска"""
        # Очищаем список сообщений
        self.messages_tree.delete(*self.messages_tree.get_children())
        
        # Заполняем список сообщений
        for message in messages:
            # Проверяем тип поля date и форматируем соответственно
            if isinstance(message['date'], str):
                try:
                    # Пробуем преобразовать ISO формат в datetime для форматирования
                    date_obj = datetime.datetime.fromisoformat(message['date'].replace('Z', '+00:00'))
                    date_str = date_obj.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    date_str = message['date']
            else:
                date_str = message['date'].strftime('%Y-%m-%d %H:%M:%S')
            
            try:
                # Получаем имя диалога, если оно есть в сообщении
                dialog_info = ""
                if 'dialog_id' in message:
                    for dialog in self.dialogs:
                        if dialog['id'] == message['dialog_id']:
                            dialog_info = f"[{dialog['name']}] "
                            break
                
                # Безопасная конкатенация строк
                sender_name = message.get('sender_name', 'Неизвестно')
                display_name = f"{dialog_info}{sender_name}" if dialog_info else sender_name
                
                # Добавляем в Treeview
                self.messages_tree.insert('', 'end', values=(
                    message['id'],
                    display_name,
                    message.get('text', '')[:100] + ('...' if len(message.get('text', '')) > 100 else ''),
                    date_str
                ))
            except Exception as e:
                self.log(f"Ошибка при отображении сообщения: {e}")
        
        # Сохраняем сообщения для последующей фильтрации
        self.messages = messages
        
        self.log(f"Отображено {len(messages)} сообщений из результатов поиска")

    def on_topic_select(self, event):
        """Обработка выбора темы"""
        selected_items = self.topics_tree.selection()
        if not selected_items:
            return
        
        item = selected_items[0]
        values = self.topics_tree.item(item, 'values')
        selected_topic_id = values[0]
        selected_topic_title = values[1]
        
        # Проверяем, выбраны ли результаты мульти-поиска
        if hasattr(self, 'search_results_topics'):
            try:
                # Получаем все выбранные темы, а не только первую
                selected_items = self.topics_tree.selection()
                if not selected_items:
                    return
                
                # Собираем все сообщения из выбранных тем
                all_messages = []
                selected_topics_info = []
                
                for item in selected_items:
                    topic_values = self.topics_tree.item(item, 'values')
                    topic_id = int(topic_values[0])
                    topic_title = topic_values[1]
                    selected_topics_info.append(f"{topic_title} (ID: {topic_id})")
                    
                    # Находим соответствующую тему в результатах поиска
                    for topic in self.search_results_topics:
                        if topic['id'] == topic_id:
                            all_messages.extend(topic['messages'])
                            break
                
                if all_messages:
                    self.log(f"Выбраны результаты поиска для чатов: {', '.join(selected_topics_info)}")
                    # Отображаем сообщения из всех выбранных тем
                    self.display_search_results_messages(all_messages)
                    return
            except (ValueError, IndexError, KeyError) as e:
                self.log(f"Ошибка при обработке результатов поиска: {e}")
        
        # Стандартная обработка выбора темы, если это не результаты поиска
        try:
            # Преобразуем ID в число
            self.selected_topic_id = int(selected_topic_id)
            self.log(f"[ТЕМА] Выбрана тема с ID: {self.selected_topic_id}, название: '{selected_topic_title}'")
            
            # Проверяем режим отображения всех сообщений
            show_all = self.show_all_messages_var.get()
            if show_all:
                self.log(f"[ТЕМА] Режим показа всех сообщений активен. Выбор темы не влияет на отображение.")
                # Обновляем только заголовок, чтобы показать что тема выбрана
                self.topics_frame.configure(text=f"Темы в: {self.selected_dialog_name} (Выбрано: {selected_topic_title})")
                return
            
            # Загружаем сообщения для выбранной темы
            self.load_topic_messages()
            
        except (ValueError, IndexError) as e:
            self.log(f"Ошибка при выборе темы: {e}")
            messagebox.showerror("Ошибка", f"Не удалось выбрать тему: {e}")
            self.selected_topic_id = None
    
    def check_topics_support(self):
        """Проверка поддержки тем в выбранном диалоге и загрузка списка тем"""
        if not hasattr(self, 'selected_dialog_id') or self.selected_dialog_id is None:
            return
            
        self.progress.start()
        
        async def run():
            try:
                # Проверяем, что клиент инициализирован
                if not self.client_manager or not hasattr(self.client_manager, 'client') or not self.client_manager.client.is_connected():
                    if not await self.client_manager.init_client():
                        self.log("Ошибка: клиент не инициализирован")
                        return
                
                # Получаем ID аккаунта
                me = await self.client_manager.client.get_me()
                account_id = str(me.phone) if me.phone else str(me.id)
                
                # Проверяем, поддерживает ли чат темы
                has_topics = await self.client_manager.has_topics(self.selected_dialog_id)
                
                if has_topics:
                    self.log(f"Диалог {self.selected_dialog_id} поддерживает темы. Загружаем список тем.")
                    
                    # Загружаем темы
                    topics = await self.client_manager.get_topics(self.selected_dialog_id)
                    
                    # Кешируем темы, если их нашли
                    if topics and self.client_manager.use_cache and self.client_manager.db_handler:
                        await self.client_manager.db_handler.cache_topics(topics, self.selected_dialog_id, account_id)
                    
                    # Если не нашли темы, но чат поддерживает их, добавим "Общее"
                    if not topics:
                        self.log("Темы не найдены, но чат поддерживает их. Добавляем тему 'Общее'")
                        topics.append({
                            'id': 1,  # Типичный ID для общей темы
                            'title': "Общее",
                            'unread_count': 0
                        })
                    
                    # Заполняем список тем
                    for topic in topics:
                        self.topics_tree.insert('', 'end', values=(
                            topic['id'],
                            topic['title'],
                            topic.get('unread_count', 0)
                        ))
                        
                    self.log(f"Загружено {len(topics)} тем")
                    
                    # Если только одна тема "Общее", сразу загружаем сообщения
                    if len(topics) == 1 and topics[0]['title'] == "Общее":
                        self.log("Найдена только общая тема, загружаем сообщения")
                        # Выбираем тему "Общее"
                        self.selected_topic_id = topics[0]['id']
                        await self.load_messages_async()
                    elif len(topics) == 0:
                        self.log("Темы поддерживаются, но не найдены. Загружаем общие сообщения.")
                        await self.load_messages_async()
                else:
                    self.log(f"Диалог {self.selected_dialog_id} не поддерживает темы. Загружаем сообщения напрямую.")
                    # Загружаем сообщения напрямую
                    await self.load_messages_async()
                    
            except Exception as e:
                self.log(f"Ошибка при проверке поддержки тем: {e}")
                import traceback
                self.log(traceback.format_exc())
            finally:
                self.progress.stop()
        
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    def toggle_show_all_messages(self):
        """Обработчик переключения режима отображения всех сообщений"""
        show_all = self.show_all_messages_var.get()
        self.log(f"[РЕЖИМ] {'Включен' if show_all else 'Выключен'} режим показа всех сообщений")
        
        # Обновляем визуальную индикацию режима
        if show_all:
            # Изменяем заголовок панели сообщений и добавляем визуальную индикацию режима
            self.messages_frame.configure(text=f"Сообщения из: {self.selected_dialog_name} (ВСЕ СООБЩЕНИЯ)")
            
            # Если есть выбранная тема, обновляем заголовок, чтобы показать выбор
            if hasattr(self, 'selected_topic_id') and self.selected_topic_id is not None:
                # Находим название темы
                selected_topic_title = "Неизвестная тема"
                for item_id in self.topics_tree.get_children():
                    item_values = self.topics_tree.item(item_id, 'values')
                    if str(item_values[0]) == str(self.selected_topic_id):
                        selected_topic_title = item_values[1]
                        break
                
                self.topics_frame.configure(text=f"Темы в: {self.selected_dialog_name} (Выбрано: {selected_topic_title})")
        else:
            # Возвращаем стандартный заголовок
            if hasattr(self, 'selected_dialog_name'):
                self.messages_frame.configure(text=f"Сообщения из: {self.selected_dialog_name}")
                self.topics_frame.configure(text=f"Темы в: {self.selected_dialog_name}")
            else:
                self.messages_frame.configure(text="Сообщения")
                self.topics_frame.configure(text="Темы")
            
            # Если есть выбранная тема, обновляем заголовок с темой
            if hasattr(self, 'selected_topic_id') and self.selected_topic_id is not None:
                # Находим название темы
                selected_topic_title = "Неизвестная тема"
                for item_id in self.topics_tree.get_children():
                    item_values = self.topics_tree.item(item_id, 'values')
                    if str(item_values[0]) == str(self.selected_topic_id):
                        selected_topic_title = item_values[1]
                        break
                
                self.messages_frame.configure(text=f"Сообщения из темы: {selected_topic_title}")
        
        # Если включен режим показа всех сообщений и диалог выбран, загружаем все сообщения
        if show_all and hasattr(self, 'selected_dialog_id') and self.selected_dialog_id:
            self.log(f"[РЕЖИМ] Загружаем все сообщения для диалога {self.selected_dialog_id}")
            self.load_messages()