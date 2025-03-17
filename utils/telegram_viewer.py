import os
import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import asyncio
import threading
from functools import partial
from typing import List, Dict, Any
import sys

# Импорт классов из основного проекта
sys.path.append('Sammaryhelper')
from Sammaryhelper.telegram_client import TelegramClientManager
from Sammaryhelper.utils import load_config, get_config_files, load_settings

class TelegramViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram Viewer")
        self.root.geometry("1200x800")
        
        # Настройка стиля приложения
        self.setup_styles()
        
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.loop = asyncio.new_event_loop()
        self.running = True
        
        # Загружаем настройки
        self.settings = self.load_settings()
        
        # Переменные для сортировки
        self.chats_sort_by = None
        self.chats_sort_reverse = False
        self.messages_sort_by = None
        self.messages_sort_reverse = False
        
        # Создаем UI
        self.setup_ui()
        
        # Инициализируем client_manager
        config_name = self.settings.get('last_config', 'config_0707')
        self.client_manager = TelegramClientManager({
            'config_name': config_name,
            'app_dir': os.path.join(self.app_dir, 'Sammaryhelper'),
            'debug': self.settings.get('debug', False)
        })
        
        # Логирование
        self.log_text = ""
        
        # Запускаем отдельный поток для обработки асинхронных операций
        self.start_async_loop()
        
        # Привязываем событие закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Инициализируем клиент перед загрузкой чатов
        self.root.after(100, self.init_client)
    
    def init_client(self):
        """Инициализация клиента Telegram"""
        self.status_label.config(text="Подключение к Telegram...")
        self.progress.start()
        
        async def init_async():
            try:
                if not self.client_manager:
                    self.log("Ошибка: менеджер клиента не инициализирован")
                    return False
                
                success = await self.client_manager.init_client()
                if success:
                    self.log("Клиент Telegram успешно инициализирован")
                    # После успешной инициализации запускаем загрузку чатов
                    self.root.after(100, self.load_chats)
                    return True
                else:
                    self.log("Ошибка при инициализации клиента Telegram")
                    return False
            except Exception as e:
                self.log(f"Ошибка при инициализации клиента: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                self.progress.stop()
        
        asyncio.run_coroutine_threadsafe(init_async(), self.loop)
    
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
        
        # Стиль для Notebook (вкладок)
        style.configure('TNotebook', background='#f0f0f0')
        style.configure('TNotebook.Tab', font=('Arial', 10, 'bold'), padding=[10, 5])
    
    def load_settings(self):
        """Загрузка настроек из файла"""
        try:
            settings_path = os.path.join(self.app_dir, 'Sammaryhelper', 'summarizer_settings.json')
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                return settings
            else:
                return {
                    'last_config': 'config_0707',
                    'max_dialogs': '100',
                    'max_messages': '100',
                    'debug': True
                }
        except Exception as e:
            print(f"Ошибка при загрузке настроек: {e}")
            return {
                'last_config': 'config_0707',
                'max_dialogs': '100',
                'max_messages': '100',
                'debug': True
            }
    
    def setup_ui(self):
        """Настройка интерфейса пользователя"""
        # Создаем основной контейнер
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill='both', expand=True)
        
        # Создаем вкладки
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Вкладка чатов
        self.chats_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.chats_frame, text="Чаты")
        
        # Вкладка сообщений
        self.messages_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.messages_frame, text="Сообщения")
        
        # Настраиваем вкладки
        self.setup_chats_tab()
        self.setup_messages_tab()
        
        # Статусная строка
        self.status_frame = ttk.Frame(self.main_frame, padding="5")
        self.status_frame.pack(fill='x', expand=False, pady=(5, 0))
        
        self.status_label = ttk.Label(self.status_frame, text="Готов", anchor='w')
        self.status_label.pack(side='left', fill='x', expand=True)
        
        self.progress = ttk.Progressbar(self.status_frame, mode='indeterminate', length=100)
        self.progress.pack(side='right', padx=5)
    
    def setup_chats_tab(self):
        """Настройка вкладки чатов"""
        # Фрейм для фильтров
        self.chats_filter_frame = ttk.LabelFrame(self.chats_frame, text="Фильтры чатов")
        self.chats_filter_frame.pack(fill='x', padx=5, pady=5)
        
        # Создаем сетку фильтров
        self.chat_filters = {}
        filter_fields = ['id', 'type', 'title', 'username', 'first_name', 'last_name', 'description']
        
        # Создаем заголовки для фильтров
        for i, field in enumerate(filter_fields):
            ttk.Label(self.chats_filter_frame, text=field).grid(row=0, column=i, padx=5, pady=5, sticky='w')
            
            # Создаем поля ввода для фильтров
            filter_var = tk.StringVar()
            filter_entry = ttk.Entry(self.chats_filter_frame, textvariable=filter_var, width=15)
            filter_entry.grid(row=1, column=i, padx=5, pady=5, sticky='w')
            
            # Связываем переменные и события
            self.chat_filters[field] = {
                'var': filter_var,
                'entry': filter_entry
            }
            
            # Привязываем событие изменения
            filter_var.trace_add('write', lambda *args, f=field: self.apply_chat_filters())
        
        # Поле для ограничения количества чатов
        ttk.Label(self.chats_filter_frame, text="Макс. чатов:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.max_chats_var = tk.StringVar(value=self.settings.get('max_dialogs', '100'))
        self.max_chats_entry = ttk.Entry(self.chats_filter_frame, textvariable=self.max_chats_var, width=5)
        self.max_chats_entry.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        
        # Кнопка загрузки чатов
        self.load_chats_btn = ttk.Button(self.chats_filter_frame, text="Загрузить чаты", command=self.load_chats)
        self.load_chats_btn.grid(row=2, column=2, padx=5, pady=5, sticky='w')
        
        # Создаем таблицу чатов
        self.chats_table_frame = ttk.LabelFrame(self.chats_frame, text="Список чатов")
        self.chats_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Создаем таблицу (дерево) с колонками
        columns = ('id', 'type', 'title', 'username', 'first_name', 'last_name', 'description')
        self.chats_tree = ttk.Treeview(self.chats_table_frame, columns=columns, show='headings')
        
        # Настраиваем колонки
        self.chats_tree.heading('id', text='ID', command=lambda: self.sort_chats_by('id'))
        self.chats_tree.heading('type', text='Тип', command=lambda: self.sort_chats_by('type'))
        self.chats_tree.heading('title', text='Название', command=lambda: self.sort_chats_by('title'))
        self.chats_tree.heading('username', text='Юзернейм', command=lambda: self.sort_chats_by('username'))
        self.chats_tree.heading('first_name', text='Имя', command=lambda: self.sort_chats_by('first_name'))
        self.chats_tree.heading('last_name', text='Фамилия', command=lambda: self.sort_chats_by('last_name'))
        self.chats_tree.heading('description', text='Описание', command=lambda: self.sort_chats_by('description'))
        
        # Устанавливаем ширину колонок
        self.chats_tree.column('id', width=100)
        self.chats_tree.column('type', width=100)
        self.chats_tree.column('title', width=200)
        self.chats_tree.column('username', width=150)
        self.chats_tree.column('first_name', width=150)
        self.chats_tree.column('last_name', width=150)
        self.chats_tree.column('description', width=300)
        
        # Добавляем скроллбар
        scrollbar = ttk.Scrollbar(self.chats_table_frame, orient=tk.VERTICAL, command=self.chats_tree.yview)
        self.chats_tree.configure(yscrollcommand=scrollbar.set)
        
        # Размещаем элементы
        self.chats_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Привязываем обработчик выбора чата
        self.chats_tree.bind('<<TreeviewSelect>>', self.on_chat_select)
    
    def sort_chats_by(self, column):
        """Сортировка чатов по выбранному столбцу"""
        self.log(f"Сортировка чатов по полю: {column}")
        
        if not hasattr(self, 'chats_data') or not self.chats_data:
            return
        
        # Если выбран тот же столбец, меняем направление сортировки
        if self.chats_sort_by == column:
            self.chats_sort_reverse = not self.chats_sort_reverse
        else:
            self.chats_sort_by = column
            self.chats_sort_reverse = False
        
        # Визуальное отображение направления сортировки
        for col in self.chats_tree['columns']:
            # Сбрасываем текст всех заголовков
            if col != column:
                self.chats_tree.heading(col, text=col.replace('_', ' ').title())
        
        # Обновляем заголовок текущего столбца
        direction = "▼" if self.chats_sort_reverse else "▲"
        self.chats_tree.heading(column, text=f"{column.replace('_', ' ').title()} {direction}")
        
        # Сортировка данных
        sorted_chats = []
        for chat in self.chats_data:
            sorted_chats.append(chat)
        
        def sort_key(chat):
            # Особая обработка для числовых полей
            if column == 'id':
                try:
                    return int(chat.get(column, 0))
                except (ValueError, TypeError):
                    return 0
            else:
                # Для текстовых полей
                return str(chat.get(column, '')).lower()
        
        sorted_chats.sort(key=sort_key, reverse=self.chats_sort_reverse)
        
        # Обновляем отображение
        self.display_chats(sorted_chats)
    
    def setup_messages_tab(self):
        """Настройка вкладки сообщений"""
        # Фрейм для фильтров
        self.messages_filter_frame = ttk.LabelFrame(self.messages_frame, text="Фильтры сообщений")
        self.messages_filter_frame.pack(fill='x', padx=5, pady=5)
        
        # Создаем сетку фильтров
        self.message_filters = {}
        filter_fields = ['message_id', 'from', 'date', 'chat', 'reply_to_message', 'text', 'message_thread_id']
        
        # Создаем заголовки для фильтров
        for i, field in enumerate(filter_fields):
            ttk.Label(self.messages_filter_frame, text=field).grid(row=0, column=i, padx=5, pady=5, sticky='w')
            
            # Создаем поля ввода для фильтров
            filter_var = tk.StringVar()
            filter_entry = ttk.Entry(self.messages_filter_frame, textvariable=filter_var, width=15)
            filter_entry.grid(row=1, column=i, padx=5, pady=5, sticky='w')
            
            # Связываем переменные и события
            self.message_filters[field] = {
                'var': filter_var,
                'entry': filter_entry
            }
            
            # Привязываем событие изменения
            filter_var.trace_add('write', lambda *args, f=field: self.apply_message_filters())
        
        # Поле для ограничения количества сообщений
        ttk.Label(self.messages_filter_frame, text="Макс. сообщений:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.max_messages_var = tk.StringVar(value=self.settings.get('max_messages', '100'))
        self.max_messages_entry = ttk.Entry(self.messages_filter_frame, textvariable=self.max_messages_var, width=5)
        self.max_messages_entry.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        
        # Отображение выбранного чата
        ttk.Label(self.messages_filter_frame, text="Выбранный чат:").grid(row=2, column=2, padx=5, pady=5, sticky='w')
        self.selected_chat_var = tk.StringVar(value="Не выбран")
        ttk.Label(self.messages_filter_frame, textvariable=self.selected_chat_var).grid(row=2, column=3, padx=5, pady=5, sticky='w')
        
        # Создаем таблицу сообщений
        self.messages_table_frame = ttk.LabelFrame(self.messages_frame, text="Список сообщений")
        self.messages_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Создаем таблицу (дерево) с колонками
        columns = ('message_id', 'from', 'date', 'chat', 'reply_to_message', 'text', 'message_thread_id')
        self.messages_tree = ttk.Treeview(self.messages_table_frame, columns=columns, show='headings')
        
        # Настраиваем колонки с сортировкой
        self.messages_tree.heading('message_id', text='ID', command=lambda: self.sort_messages_by('message_id'))
        self.messages_tree.heading('from', text='От', command=lambda: self.sort_messages_by('from'))
        self.messages_tree.heading('date', text='Дата', command=lambda: self.sort_messages_by('date'))
        self.messages_tree.heading('chat', text='Чат', command=lambda: self.sort_messages_by('chat'))
        self.messages_tree.heading('reply_to_message', text='Ответ на', command=lambda: self.sort_messages_by('reply_to_message'))
        self.messages_tree.heading('text', text='Текст', command=lambda: self.sort_messages_by('text'))
        self.messages_tree.heading('message_thread_id', text='ID темы', command=lambda: self.sort_messages_by('message_thread_id'))
        
        # Устанавливаем ширину колонок
        self.messages_tree.column('message_id', width=100)
        self.messages_tree.column('from', width=150)
        self.messages_tree.column('date', width=150)
        self.messages_tree.column('chat', width=150)
        self.messages_tree.column('reply_to_message', width=100)
        self.messages_tree.column('text', width=300)
        self.messages_tree.column('message_thread_id', width=100)
        
        # Добавляем скроллбар по вертикали
        scrollbar_y = ttk.Scrollbar(self.messages_table_frame, orient=tk.VERTICAL, command=self.messages_tree.yview)
        self.messages_tree.configure(yscrollcommand=scrollbar_y.set)
        
        # Добавляем скроллбар по горизонтали
        scrollbar_x = ttk.Scrollbar(self.messages_table_frame, orient=tk.HORIZONTAL, command=self.messages_tree.xview)
        self.messages_tree.configure(xscrollcommand=scrollbar_x.set)
        
        # Размещаем элементы
        self.messages_tree.pack(side='left', fill='both', expand=True)
        scrollbar_y.pack(side='right', fill='y')
        scrollbar_x.pack(side='bottom', fill='x')
        
        # Привязываем обработчики событий
        self.messages_tree.bind('<<TreeviewSelect>>', self.on_message_select)
        self.messages_tree.bind('<Double-1>', self.show_message_details)  # Двойной клик для подробных сведений
    
    def sort_messages_by(self, column):
        """Сортировка сообщений по выбранному столбцу"""
        self.log(f"Сортировка сообщений по полю: {column}")
        
        if not hasattr(self, 'messages_data') or not self.messages_data:
            return
        
        # Если выбран тот же столбец, меняем направление сортировки
        if self.messages_sort_by == column:
            self.messages_sort_reverse = not self.messages_sort_reverse
        else:
            self.messages_sort_by = column
            self.messages_sort_reverse = False
        
        # Визуальное отображение направления сортировки
        for col in self.messages_tree['columns']:
            # Сбрасываем текст всех заголовков
            if col != column:
                if col == 'message_id':
                    self.messages_tree.heading(col, text='ID')
                elif col == 'message_thread_id':
                    self.messages_tree.heading(col, text='ID темы')
                else:
                    self.messages_tree.heading(col, text=col.replace('_', ' ').title())
        
        # Обновляем заголовок текущего столбца
        direction = "▼" if self.messages_sort_reverse else "▲"
        if column == 'message_id':
            self.messages_tree.heading(column, text=f"ID {direction}")
        elif column == 'message_thread_id':
            self.messages_tree.heading(column, text=f"ID темы {direction}")
        else:
            self.messages_tree.heading(column, text=f"{column.replace('_', ' ').title()} {direction}")
        
        # Сортировка данных
        sorted_messages = []
        for message in self.messages_data:
            sorted_messages.append(message)
        
        def sort_key(message):
            # Особая обработка для числовых полей
            if column in ['message_id', 'message_thread_id']:
                try:
                    return int(message.get(column, 0))
                except (ValueError, TypeError):
                    return 0
            elif column == 'date':
                # Для даты особая сортировка, так как это строка, но должна сортироваться как дата
                return message.get(column, '')
            else:
                # Для текстовых полей
                return str(message.get(column, '')).lower()
        
        sorted_messages.sort(key=sort_key, reverse=self.messages_sort_reverse)
        
        # Обновляем отображение
        self.display_messages(sorted_messages)
    
    def start_async_loop(self):
        """Запуск асинхронного цикла в отдельном потоке"""
        def run_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()
    
    def log(self, message):
        """Логирование"""
        if self.settings.get('debug', False):
            print(f"[DEBUG] {message}")
            self.log_text += f"{message}\n"
            # Обновляем статусную строку
            self.status_label.config(text=message)
    
    def on_close(self):
        """Обработка закрытия окна"""
        self.running = False
        
        async def close_async():
            # Закрываем соединение с Telegram
            if self.client_manager:
                await self.client_manager.close()
            
            # Останавливаем цикл
            for task in asyncio.all_tasks(self.loop):
                task.cancel()
            
            self.loop.stop()
        
        # Запускаем асинхронную задачу закрытия
        asyncio.run_coroutine_threadsafe(close_async(), self.loop)
        
        # Дожидаемся завершения потока
        self.thread.join(timeout=1.0)
        
        # Закрываем окно
        self.root.destroy()
    
    def load_chats(self):
        """Загрузка списка чатов"""
        self.progress.start()
        self.load_chats_btn.state(['disabled'])
        
        async def run():
            try:
                # Проверяем, что клиент инициализирован
                if not self.client_manager or not self.client_manager.client:
                    if not await self.client_manager.init_client():
                        self.log("Ошибка: клиент не инициализирован")
                        return
                
                if not self.client_manager.client.is_connected():
                    await self.client_manager.client.connect()
                    if not self.client_manager.client.is_connected():
                        self.log("Ошибка: не удалось подключиться к Telegram")
                        return
                
                self.log("Загрузка списка чатов...")
                
                # Получаем диалоги через API
                dialogs = await self.client_manager.get_dialogs()
                
                # Лимит на количество чатов
                try:
                    max_chats = int(self.max_chats_var.get())
                except ValueError:
                    max_chats = 100
                
                # Преобразуем в нужный формат
                chats = []
                for i, dialog in enumerate(dialogs):
                    if i >= max_chats:
                        break
                    
                    entity = dialog['entity']
                    
                    # Определяем тип чата
                    chat_type = dialog['type']
                    if chat_type == "Канал":
                        chat_type = "channel"
                    elif chat_type == "Чат":
                        if hasattr(entity, 'megagroup') and entity.megagroup:
                            chat_type = "supergroup"
                        else:
                            chat_type = "group"
                    else:
                        chat_type = "private"
                    
                    # Создаем запись чата
                    chat_info = {
                        'id': dialog['id'],
                        'type': chat_type,
                        'title': getattr(entity, 'title', ''),
                        'username': getattr(entity, 'username', ''),
                        'first_name': getattr(entity, 'first_name', ''),
                        'last_name': getattr(entity, 'last_name', ''),
                        'description': getattr(entity, 'about', '')
                    }
                    chats.append(chat_info)
                
                # Сохраняем данные для фильтрации
                self.chats_data = chats
                
                # Отображаем в интерфейсе
                self.display_chats(chats)
                
                self.log(f"Загружено {len(chats)} чатов")
            except Exception as e:
                self.log(f"Ошибка при загрузке чатов: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self.progress.stop()
                self.load_chats_btn.state(['!disabled'])
        
        asyncio.run_coroutine_threadsafe(run(), self.loop)
    
    def display_chats(self, chats):
        """Отображение списка чатов в таблице"""
        # Очищаем таблицу
        for item in self.chats_tree.get_children():
            self.chats_tree.delete(item)
        
        # Добавляем данные
        for chat in chats:
            self.chats_tree.insert('', 'end', values=(
                chat['id'],
                chat['type'],
                chat['title'],
                chat['username'],
                chat['first_name'],
                chat['last_name'],
                chat['description']
            ))
    
    def apply_chat_filters(self):
        """Применение фильтров к чатам"""
        if not hasattr(self, 'chats_data'):
            return
        
        # Получаем значения фильтров
        filters = {
            field: self.chat_filters[field]['var'].get().lower()
            for field in self.chat_filters
        }
        
        # Фильтруем данные
        filtered_chats = []
        for chat in self.chats_data:
            should_include = True
            
            for field, filter_text in filters.items():
                if filter_text and str(chat.get(field, '')).lower().find(filter_text) == -1:
                    should_include = False
                    break
            
            if should_include:
                filtered_chats.append(chat)
        
        # Отображаем отфильтрованные данные
        self.display_chats(filtered_chats)
    
    def on_chat_select(self, event):
        """Обработка выбора чата"""
        selected_items = self.chats_tree.selection()
        if not selected_items:
            return
        
        # Получаем ID выбранного чата
        item = selected_items[0]
        values = self.chats_tree.item(item, 'values')
        chat_id = values[0]
        chat_title = values[2] or f"{values[4]} {values[5]}"  # Название или имя+фамилия
        
        # Сохраняем ID выбранного чата
        self.selected_chat_id = int(chat_id)
        self.selected_chat_var.set(f"ID: {chat_id}, {chat_title}")
        
        self.log(f"Выбран чат: {chat_title} (ID: {chat_id})")
        
        # Загружаем сообщения для выбранного чата
        self.open_messages_tab()
    
    def open_messages_tab(self):
        """
        Открыть вкладку сообщений и загрузить сообщения из выбранного чата.
        """
        if not self.selected_chat_id:
            messagebox.showwarning("Предупреждение", "Выберите чат для просмотра сообщений")
            return
            
        self.log(f"Открытие вкладки сообщений для чата {self.selected_chat_id} ({self.selected_chat_var.get()})")
        
        # Переключиться на вкладку сообщений
        self.notebook.select(1)  # Индекс вкладки "Сообщения"
        
        # Загрузить сообщения
        self.load_messages_wrapper()
    
    def load_messages_wrapper(self):
        """
        Обертка для асинхронного метода load_messages с индикатором прогресса.
        """
        self.progress.start()
        
        async def run():
            try:
                # Проверить, что клиент инициализирован
                if not self.client_manager or not hasattr(self.client_manager, 'client') or not self.client_manager.client:
                    self.log("Инициализация клиента...")
                    await self.init_client()
                
                if not self.client_manager.client.is_connected():
                    self.log("Клиент не подключен, подключаемся...")
                    await self.client_manager.client.connect()
                    if not self.client_manager.client.is_connected():
                        self.log("Ошибка: не удалось подключиться к Telegram")
                        messagebox.showerror("Ошибка", "Не удалось подключиться к Telegram")
                        return
                
                # Получаем лимит сообщений
                try:
                    max_messages = int(self.max_messages_var.get())
                except ValueError:
                    max_messages = 100
                
                # Вызвать асинхронный метод загрузки сообщений с указанием лимита
                await self.load_messages(max_messages)
            except Exception as e:
                self.log(f"Ошибка при загрузке сообщений: {e}")
                import traceback
                self.log(traceback.format_exc())
                messagebox.showerror("Ошибка", f"Не удалось загрузить сообщения: {e}")
            finally:
                self.progress.stop()
        
        # Запустить асинхронную задачу
        asyncio.run_coroutine_threadsafe(run(), self.loop)
    
    async def load_messages(self, limit=100):
        """
        Загрузить сообщения из выбранного чата.
        """
        if not self.selected_chat_id:
            self.log("Не выбран чат для загрузки сообщений.")
            return

        chat_id = self.selected_chat_id
        self.log(f"Загрузка сообщений из чата {chat_id}, лимит: {limit}")
        
        # Получить сообщения через клиент-менеджер
        messages = await self.client_manager.get_messages(chat_id, limit=limit)
        
        # Попробуем получить raw-сообщения для более полной информации
        raw_messages = []
        try:
            raw_messages = await self.client_manager.get_raw_messages(chat_id, limit=limit)
            self.log(f"Получено {len(raw_messages)} raw-сообщений")
        except Exception as e:
            self.log(f"Ошибка при получении raw-сообщений: {e}")
            
        # Создадим словарь raw_messages по id для быстрого доступа
        raw_messages_dict = {}
        for message in raw_messages:
            raw_messages_dict[message.id] = message
        
        # Очистить таблицу сообщений
        for item in self.messages_tree.get_children():
            self.messages_tree.delete(item)
            
        if not messages:
            self.log("Не удалось загрузить сообщения")
            return
            
        self.log(f"Загружено {len(messages)} сообщений")
        
        # Создаем список для хранения всех сообщений (для фильтрации)
        messages_data = []
        
        # Добавить сообщения в таблицу
        for message in messages:
            # Выводим структуру сообщения для отладки
            self.log(f"Все ключи: {', '.join(message.keys())}")
            self.log(f"Структура сообщения ID {message['id']}:")
            
            # Проверяем, есть ли информация о reply_to в raw_message
            reply_to_msg_id = ""
            if message['id'] in raw_messages_dict:
                raw_message = raw_messages_dict[message['id']]
                if hasattr(raw_message, 'reply_to'):
                    self.log(f"Сообщение {message['id']} имеет reply_to: {raw_message.reply_to}")
                    # Если reply_to - это объект, пытаемся получить reply_to_msg_id
                    if hasattr(raw_message.reply_to, 'reply_to_msg_id'):
                        reply_to_msg_id = raw_message.reply_to.reply_to_msg_id
                        self.log(f"Сообщение {message['id']} отвечает на сообщение {reply_to_msg_id}")
                    # Альтернативно проверим, является ли reply_to словарем
                    elif isinstance(raw_message.reply_to, dict) and 'reply_to_msg_id' in raw_message.reply_to:
                        reply_to_msg_id = raw_message.reply_to['reply_to_msg_id']
                        self.log(f"Сообщение {message['id']} отвечает на сообщение {reply_to_msg_id} (из словаря)")
                # Проверяем дополнительные поля, которые могут содержать ID оригинального сообщения
                elif hasattr(raw_message, 'reply_to_message_id') and raw_message.reply_to_message_id:
                    reply_to_msg_id = raw_message.reply_to_message_id
                    self.log(f"Сообщение {message['id']} отвечает на сообщение {reply_to_msg_id} (из reply_to_message_id)")
                elif hasattr(raw_message, 'reply_to_msg_id') and raw_message.reply_to_msg_id:
                    reply_to_msg_id = raw_message.reply_to_msg_id
                    self.log(f"Сообщение {message['id']} отвечает на сообщение {reply_to_msg_id} (из reply_to_msg_id)")
            
            message_data = {
                'message_id': message['id'],
                'from': message['sender_name'],
                'date': message['date'],
                'chat': self.selected_chat_var.get(),
                'reply_to_message': reply_to_msg_id,
                'text': message['text'],
                'message_thread_id': message.get('message_thread_id', '')
            }
            
            # Добавляем в общий список
            messages_data.append(message_data)
        
        # Сохраняем данные для фильтрации
        self.messages_data = messages_data
        
        # Отображаем сообщения в интерфейсе
        self.display_messages(messages_data)
        
        self.log(f"Сообщения успешно загружены и отображены")
    
    def display_messages(self, messages):
        """Отображение списка сообщений в таблице"""
        # Очищаем таблицу
        for item in self.messages_tree.get_children():
            self.messages_tree.delete(item)
        
        # Добавляем данные
        for message in messages:
            self.messages_tree.insert('', 'end', values=(
                message['message_id'],
                message['from'],
                message['date'],
                message['chat'],
                message['reply_to_message'],
                message['text'][:50] + ('...' if len(message['text']) > 50 else ''),
                message['message_thread_id']
            ))
    
    def apply_message_filters(self):
        """Применение фильтров к сообщениям"""
        if not hasattr(self, 'messages_data'):
            return
        
        # Получаем значения фильтров
        filters = {
            field: self.message_filters[field]['var'].get().lower()
            for field in self.message_filters
        }
        
        # Фильтруем данные
        filtered_messages = []
        for message in self.messages_data:
            should_include = True
            
            for field, filter_text in filters.items():
                if filter_text and str(message.get(field, '')).lower().find(filter_text) == -1:
                    should_include = False
                    break
            
            if should_include:
                filtered_messages.append(message)
        
        # Отображаем отфильтрованные данные
        self.display_messages(filtered_messages)
    
    def on_message_select(self, event):
        """Обработка выбора сообщения"""
        selected_items = self.messages_tree.selection()
        if not selected_items:
            return
        
        # Получаем ID выбранного сообщения
        item = selected_items[0]
        values = self.messages_tree.item(item, 'values')
        message_id = values[0]
        
        self.log(f"Выбрано сообщение: ID {message_id}")
        
        # Находим сообщение в данных
        selected_message = None
        for message in self.messages_data:
            if str(message['message_id']) == str(message_id):
                selected_message = message
                break
        
        if selected_message:
            # Показываем информацию о сообщении в всплывающем окне
            text = f"ID: {selected_message['message_id']}\n"
            text += f"От: {selected_message['from']}\n"
            text += f"Дата: {selected_message['date']}\n"
            text += f"Чат: {selected_message['chat']}\n"
            
            # Добавляем информацию о сообщении, на которое был ответ
            if selected_message.get('reply_to_message'):
                text += f"Ответ на сообщение: {selected_message['reply_to_message']}\n"
                
                # Попытка найти текст сообщения, на которое отвечали
                reply_id = selected_message['reply_to_message']
                reply_text = "Текст сообщения недоступен"
                
                for msg in self.messages_data:
                    if str(msg['message_id']) == str(reply_id):
                        reply_text = msg['text'][:100] + ('...' if len(msg['text']) > 100 else '')
                        break
                
                text += f"Текст сообщения, на которое отвечали:\n{reply_text}\n"
            
            if selected_message.get('message_thread_id'):
                text += f"ID темы: {selected_message['message_thread_id']}\n"
            
            text += f"\nТекст сообщения:\n{selected_message['text']}"
            
            # Создаём окно с большей шириной и возможностью прокрутки
            dialog = tk.Toplevel(self.root)
            dialog.title(f"Сообщение ID: {selected_message['message_id']}")
            dialog.geometry("600x400")
            
            text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, width=70, height=20)
            text_widget.insert(tk.END, text)
            text_widget.config(state=tk.DISABLED)  # Делаем текст только для чтения
            text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Кнопка закрытия
            close_button = ttk.Button(dialog, text="Закрыть", command=dialog.destroy)
            close_button.pack(pady=10)

    def show_message_details(self, event):
        """
        Показать подробную информацию о выбранном сообщении.
        """
        selected_item = self.messages_tree.selection()
        if not selected_item:
            return
            
        # Получить данные выбранного сообщения
        item_data = self.messages_tree.item(selected_item[0])
        values = item_data['values']
        
        if not values:
            return
            
        # Распаковать значения
        message_id, sender, date, chat, reply_to_message, text, message_thread_id = values
        
        # Подготовить детальную информацию о сообщении
        message_details = f"ID сообщения: {message_id}\n"
        message_details += f"Отправитель: {sender}\n"
        message_details += f"Дата: {date}\n"
        message_details += f"Чат: {chat}\n"
        
        # Добавить информацию о сообщении, на которое был сделан ответ, если есть
        if reply_to_message:
            message_details += f"Ответ на сообщение ID: {reply_to_message}\n"
            
            # Попытаться найти текст сообщения, на которое был сделан ответ
            reply_text = "Неизвестно"
            for item in self.messages_tree.get_children():
                reply_item_data = self.messages_tree.item(item)
                reply_values = reply_item_data['values']
                if reply_values and reply_values[0] == reply_to_message:
                    reply_text = reply_values[5]  # Текст сообщения
                    reply_sender = reply_values[1]  # Отправитель
                    message_details += f"Оригинальное сообщение от {reply_sender}: {reply_text}\n"
                    break
        
        # Добавить информацию о теме, если есть
        if message_thread_id:
            message_details += f"ID темы: {message_thread_id}\n"
            
        message_details += f"\nТекст сообщения:\n{text}"
        
        # Создать новое окно для отображения деталей сообщения
        message_window = tk.Toplevel(self.root)
        message_window.title(f"Информация о сообщении {message_id}")
        message_window.geometry("600x400")
        
        # Добавить поле для отображения текста с возможностью прокрутки
        from tkinter.scrolledtext import ScrolledText
        message_text = ScrolledText(message_window, wrap=tk.WORD)
        message_text.insert(tk.END, message_details)
        message_text.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        message_text.config(state=tk.DISABLED)  # Запретить редактирование
        
        # Добавить кнопку для закрытия окна
        close_button = ttk.Button(message_window, text="Закрыть", command=message_window.destroy)
        close_button.pack(pady=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = TelegramViewer(root)
    root.mainloop() 