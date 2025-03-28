# Пользовательский интерфейс Sammaryhelper

## Обзор интерфейса

Sammaryhelper предоставляет графический пользовательский интерфейс (GUI) на основе библиотеки Tkinter. Интерфейс разработан для обеспечения удобного доступа к функциональности приложения и эффективной работы с диалогами Telegram.

## Структура интерфейса

Интерфейс организован в виде вкладок и панелей, что позволяет логически разделить различные функции приложения:

### 1. Основная вкладка

Основная вкладка содержит главный функционал приложения и разделена на несколько панелей:

#### 1.1. Панель расширенного поиска
- Расположена в верхней части интерфейса
- Предоставляет возможность поиска по нескольким чатам одновременно
- Содержит поля для ввода критериев поиска:
  - Текст сообщения
  - Отправитель
  - Дата
  - Статус ответа
- Включает кнопку для выполнения поиска

#### 1.2. Панель диалогов
- Расположена в левой части интерфейса
- Отображает список доступных диалогов (чаты, группы, каналы)
- Содержит фильтры для поиска и сортировки диалогов
- Поддерживает множественный выбор диалогов для поиска

#### 1.3. Панель тем
- Расположена в центральной части интерфейса
- Отображает темы для выбранного диалога (для супергрупп)
- Показывает результаты поиска по нескольким чатам

#### 1.4. Панель сообщений
- Расположена в правой части интерфейса
- Отображает сообщения из выбранного диалога или темы
- Содержит фильтры для поиска и сортировки сообщений
- Включает просмотр полного текста выбранного сообщения

#### 1.5. Панель чата с ИИ
- Расположена в нижней части интерфейса
- Позволяет задавать вопросы ИИ о выбранных сообщениях
- Отображает ответы ИИ и историю взаимодействия

#### 1.6. Панель логов
- Расположена в нижней части интерфейса
- Отображает логи работы приложения
- Помогает в отладке и понимании процессов

### 2. Вкладка конфигурации

Вкладка конфигурации предоставляет доступ к настройкам подключения к Telegram API:

- Выбор конфигурационного файла
- Настройка API ID и API Hash для Telegram
- Настройка прокси (опционально)
- Настройка OpenAI API ключа
- Настройка подключения к базе данных PostgreSQL

### 3. Вкладка настроек

Вкладка настроек позволяет настроить параметры работы приложения:

- Выбор модели OpenAI для генерации суммаризаций
- Настройка системного промпта для ИИ
- Включение/выключение режима отладки
- Настройка параметров клиента Telegram (версия системы, модель устройства, версия приложения)

## Компоненты интерфейса

### 1. Основные виджеты

#### 1.1. Treeview
- Используется для отображения списков (диалоги, темы, сообщения)
- Поддерживает сортировку по столбцам
- Поддерживает множественный выбор элементов

#### 1.2. Entry и Combobox
- Используются для ввода текста и выбора из списка
- Применяются в фильтрах и полях поиска

#### 1.3. Button
- Используется для выполнения действий
- Основные кнопки: "Загрузить диалоги", "Сообщения", "Применить фильтры", "Искать"

#### 1.4. Checkbutton
- Используется для включения/выключения опций
- Пример: "Показать все сообщения", "Дебаг"

#### 1.5. ScrolledText
- Используется для отображения больших текстов
- Применяется в панели логов, чате с ИИ, просмотре сообщений

#### 1.6. PanedWindow
- Используется для создания разделяемых панелей
- Позволяет пользователю изменять размеры панелей

#### 1.7. LabelFrame
- Используется для группировки связанных элементов
- Предоставляет визуальное разделение и заголовки для секций

### 2. Стилизация интерфейса

Интерфейс использует стилизацию для улучшения внешнего вида:

```python
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
```

## Взаимодействие с пользователем

### 1. Обработка событий

Интерфейс обрабатывает различные события пользователя:

#### 1.1. Выбор диалога
```python
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
    
    # Обновляем статус выбора для расширенного поиска
    self.update_dialogs_selection_status()
    
    # Если выбран только один диалог, обрабатываем его для отображения тем и сообщений
    if len(selected_items) == 1:
        # ...
```

#### 1.2. Выбор темы
```python
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
        # ...
    
    # Стандартная обработка выбора темы
    try:
        # Преобразуем ID в число
        self.selected_topic_id = int(selected_topic_id)
        # ...
```

#### 1.3. Выбор сообщения
```python
def on_message_select(self, event):
    """Обработчик выбора сообщения"""
    selected_items = self.messages_tree.selection()
    if not selected_items:
        return
    
    # Получаем ID выбранного сообщения
    message_id = self.messages_tree.item(selected_items[0])['values'][0]
    
    # Находим сообщение по ID в списке messages
    selected_message = None
    for message in self.messages:
        if str(message['id']) == str(message_id):
            selected_message = message
            break
    
    # Отображаем полный текст сообщения
    if selected_message:
        # ...
```

### 2. Асинхронные операции

Интерфейс выполняет асинхронные операции в отдельном потоке, чтобы не блокировать GUI:

```python
def load_filtered_dialogs(self):
    """Загрузка и фильтрация диалогов"""
    self.progress.start()
    self.load_dialogs_btn.state(['disabled'])
    
    async def run():
        try:
            # Асинхронные операции
            # ...
        except Exception as e:
            self.log(f"Ошибка при загрузке диалогов: {e}")
        finally:
            self.progress.stop()
            self.load_dialogs_btn.state(['!disabled'])
    
    asyncio.run_coroutine_threadsafe(run(), self.loop)
```

### 3. Индикация прогресса

Для длительных операций используется индикатор прогресса:

```python
# Индикатор прогресса
self.progress = ttk.Progressbar(self.main_frame, mode='indeterminate')
self.progress.pack(fill=tk.X, padx=5, pady=5)
```

### 4. Обратная связь

Интерфейс предоставляет обратную связь пользователю через:

- Логи в текстовом поле
- Сообщения об ошибках
- Обновление заголовков панелей с информацией о выбранных элементах
- Индикацию состояния кнопок (enabled/disabled)

## Особенности реализации

### 1. Модульная структура

Интерфейс разделен на логические модули для улучшения поддерживаемости:

```python
def __init__(self, root):
    # ...
    self.setup_styles()
    # ...
    self.setup_main_tab()
    self.setup_config_tab()
    self.setup_settings_tab()
    self.setup_search_frame()
    # ...
```

### 2. Сохранение состояния

Интерфейс сохраняет свое состояние между запусками:

```python
def save_window_state(self):
    """Сохранение состояния окна"""
    try:
        settings_path = os.path.join(self.app_dir, 'configs', 'sh_profile.json')
        # ...
        geometry = self.root.geometry()
        # ...
        settings['window_state'] = {
            'geometry': geometry
        }
        # ...
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        # ...
```

### 3. Логирование

Интерфейс включает систему логирования для отладки:

```python
def log(self, message):
    """Логирование сообщений"""
    if self.debug_var.get():
        print(message)
    
    # Добавляем сообщение в лог-виджет, если он существует
    if hasattr(self, 'log_text') and self.log_text:
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
```

## Планы по улучшению интерфейса

### 1. Улучшение визуализации результатов поиска
- Добавление подсветки найденных фрагментов текста
- Улучшение отображения результатов поиска по нескольким чатам
- Добавление графиков и диаграмм для анализа активности

### 2. Оптимизация интерфейса
- Улучшение производительности при работе с большими списками
- Оптимизация обновления интерфейса при асинхронных операциях
- Добавление виртуализации списков для эффективной работы с большими наборами данных

### 3. Расширение функциональности
- Добавление возможности экспорта результатов
- Реализация дополнительных фильтров и параметров поиска
- Добавление визуального редактора системного промпта для ИИ

### 4. Улучшение доступности
- Добавление горячих клавиш для основных операций
- Улучшение навигации с клавиатуры
- Поддержка масштабирования интерфейса

## Рекомендации по работе с интерфейсом

1. **Использование множественного выбора диалогов**:
   - Удерживайте Ctrl при клике для выбора нескольких диалогов
   - Используйте расширенный поиск для поиска по нескольким чатам

2. **Эффективная работа с темами**:
   - Используйте переключатель "Показать все сообщения" для отображения всех сообщений в диалоге
   - Выбирайте темы для фильтрации сообщений в супергруппах

3. **Оптимизация поиска**:
   - Используйте комбинацию фильтров для точного поиска
   - Ограничивайте количество сообщений для улучшения производительности

4. **Работа с ИИ**:
   - Выбирайте сообщения перед отправкой запроса к ИИ для предоставления контекста
   - Настраивайте системный промпт для получения более релевантных ответов