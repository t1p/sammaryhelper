from .telegram_client_base import TelegramClientBase
from .telegram_client_messages import TelegramClientMessages
from .telegram_client_dialogs import TelegramClientDialogs
from typing import List, Dict, Any

class TelegramClientManager(TelegramClientDialogs, TelegramClientMessages):
    """
    Основной класс для работы с Telegram API.
    Объединяет функциональность базового клиента, работы с сообщениями и диалогами.
    """
    
    # Так как TelegramClientManager наследуется от TelegramClientDialogs,
    # который в свою очередь наследуется от TelegramClientBase,
    # то все методы из обоих классов доступны в TelegramClientManager.
    
    # При необходимости здесь можно переопределить методы родительских классов
    # или добавить новую функциональность, специфичную для TelegramClientManager.
    
    pass  # Так как вся функциональность уже определена в родительских классах