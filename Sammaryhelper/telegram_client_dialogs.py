from telethon.tl.types import Channel, User
from telethon.tl import functions
from typing import List, Dict, Any
import datetime
import traceback
from .telegram_client_base import TelegramClientBase

class TelegramClientDialogs(TelegramClientBase):
    """Класс для работы с диалогами и поиском в Telegram API"""
    
    async def get_dialogs(self):
        """Получение списка диалогов с информацией о папках"""
        dialogs = []
        folders = await self.get_dialog_folders()
        
        async for dialog in self.client.iter_dialogs():
            dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
            
            # Определяем папку для диалога
            folder_info = None
            if hasattr(dialog, 'folder') and dialog.folder:
                folder_id = dialog.folder.id
                if folder_id in folders:
                    folder_info = {
                        'id': folder_id,
                        'title': folders[folder_id]['title']
                    }
            
            dialogs.append({
                'id': dialog.id,
                'name': dialog.name,
                'type': dialog_type,
                'entity': dialog.entity,
                'folder': folder_info,
                'unread_count': getattr(dialog, 'unread_count', 0)
            })
        return dialogs

    async def get_chat_participants(self, chat_id: int) -> List[Dict[str, Any]]:
        """Получение списка участников чата"""
        try:
            participants = []
            async for user in self.client.iter_participants(chat_id):
                participants.append({
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                })
            return participants
        except Exception as e:
            raise Exception(f"Ошибка при получении участников чата: {e}")

    async def get_dialog_folders(self) -> Dict[int, Dict[str, Any]]:
        """Получение структуры папок через Telegram API"""
        try:
            folders = {}
            
            # Пробуем получить папки через GetDialogFiltersRequest
            try:
                result = await self.client(functions.messages.GetDialogFiltersRequest())
                for folder in result:
                    folders[folder.id] = {
                        'title': folder.title,
                        'id': folder.id,
                        'dialogs': []
                    }
                    # Получаем диалоги для каждой папки
                    dialogs = await self.client.get_dialogs(folder=folder.id)
                    folders[folder.id]['dialogs'] = [d.id for d in dialogs]
            except AttributeError:
                # Fallback для старых версий или если метод не доступен
                dialogs = await self.client.get_dialogs(folder=0)
                for dialog in dialogs:
                    if hasattr(dialog, 'folder') and dialog.folder:
                        if dialog.folder.id not in folders:
                            folders[dialog.folder.id] = {
                                'title': f"Папка {dialog.folder.id}",
                                'id': dialog.folder.id,
                                'dialogs': []
                            }
                        folders[dialog.folder.id]['dialogs'].append(dialog.id)
            
            return folders
        except Exception as e:
            self.log(f"Ошибка при получении папок: {e}")
            return {}

    async def filter_dialogs(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Фильтрация диалогов по заданным критериям"""
        try:
            self.log(f"Вызов filter_dialogs с фильтрами: {filters}")
            
            # Проверяем лимит
            limit = filters.get('limit')
            search_query = filters.get('search', '')
            force_refresh = filters.get('force_refresh', False)
            
            self.log(f"Полученный лимит для диалогов: {limit}, поиск: '{search_query}', обновление: {force_refresh}. Используем кеш: {self.use_cache}")
            
            # Получаем ID аккаунта
            me = await self.client.get_me()
            if me is None:
                self.log("Ошибка: Не удалось получить информацию о текущем пользователе (me is None).")
                account_id = "" # Или можно выбросить исключение, в зависимости от желаемого поведения
            else:
                account_id = str(me.phone) if me.phone else me.username
            self.log(f"ID аккаунта: {account_id}")
            
            # Получаем структуру папок
            folders = await self.get_dialog_folders()
            
            # Используем кеш для получения данных только если не требуется обновление
            dialogs = []
            use_cache = self.use_cache and self.db_handler
            
            if use_cache:
                # Загружаем диалоги из кеша
                cached_dialogs = await self.db_handler.get_cached_dialogs(account_id, limit)
                self.log(f"Получено {len(cached_dialogs)} кешированных диалогов из БД")
                
                # Определяем, нужно ли обновление кеша
                update_cache = force_refresh or (len(cached_dialogs) < limit and not search_query)
                
                if update_cache:
                    self.log(f"Обновление кеша диалогов (force_refresh: {force_refresh}, cache_size: {len(cached_dialogs)}, limit: {limit})")
                    api_dialogs = []
                    
                    # Загружаем диалоги из Telegram API
                    async for dialog in self.client.iter_dialogs(limit=limit):
                        dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
                        
                        # Определяем папку для диалога
                        folder_info = None
                        if hasattr(dialog, 'folder') and dialog.folder:
                            folder_id = dialog.folder.id
                            if folder_id in folders:
                                folder_info = {
                                    'id': folder_id,
                                    'title': folders[folder_id]['title']
                                }
                        
                        api_dialogs.append({
                            'id': dialog.id,
                            'name': dialog.name,
                            'type': dialog_type,
                            'entity': dialog.entity,
                            'folder': folder_info,
                            'unread_count': getattr(dialog, 'unread_count', 0)
                        })
                    
                    self.log(f"Получено {len(api_dialogs)} диалогов из Telegram API")
                    
                    # Кешируем диалоги из API
                    dialogs_to_cache = []
                    for dialog in api_dialogs:
                        dialog_copy = {
                            'id': dialog['id'],
                            'name': dialog['name'],
                            'type': dialog['type'],
                            'folder': dialog['folder'],
                            'unread_count': dialog['unread_count']
                        }
                        if 'entity' in dialog_copy:
                            del dialog_copy['entity']
                        dialogs_to_cache.append(dialog_copy)
                    
                    self.log(f"Кеширование {len(dialogs_to_cache)} диалогов в БД")
                    await self.db_handler.cache_dialogs(dialogs_to_cache, account_id)
                    
                    # Объединяем с кешированными диалогами
                    merged_dialogs = {}
                    
                    # Сначала добавляем диалоги из API
                    for dialog in api_dialogs:
                        merged_dialogs[dialog['id']] = dialog
                    
                    # Затем добавляем остальные из кеша, если их нет в результате API и не превышен лимит
                    for dialog in cached_dialogs:
                        if dialog['id'] not in merged_dialogs and len(merged_dialogs) < limit:
                            merged_dialogs[dialog['id']] = dialog
                    
                    # Преобразуем обратно в список
                    dialogs = list(merged_dialogs.values())
                else:
                    # Используем только кешированные данные для поиска
                    self.log(f"Используем только кешированные диалоги для поиска '{search_query}'")
                    dialogs = cached_dialogs
            else:
                self.log("Кеширование отключено, загружаем диалоги из API.")
                async for dialog in self.client.iter_dialogs(limit=limit):
                    dialog_type = "Канал" if isinstance(dialog.entity, Channel) else "Чат" if dialog.is_group else "Личка"
                    dialogs.append({
                        'id': dialog.id,
                        'name': dialog.name,
                        'type': dialog_type,
                        'entity': dialog.entity,
                        'folder_id': dialog.folder if hasattr(dialog, 'folder') else None,
                        'unread_count': getattr(dialog, 'unread_count', 0)
                    })
            
            return dialogs
        except Exception as e:
            self.log(f"Ошибка при фильтрации диалогов: {e}")
            raise
