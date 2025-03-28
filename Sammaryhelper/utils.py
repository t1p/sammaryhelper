import os
import json
import importlib.util
from typing import List, Dict, Any

def load_config(config_path: str) -> Any:
    """Загрузка конфигурационного файла"""
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

def get_config_files(app_dir: str) -> List[str]:
    """Получение списка конфигурационных файлов"""
    configs = []
    configs_dir = os.path.join(app_dir, "configs")
    if not os.path.exists(configs_dir):
        os.makedirs(configs_dir)
        create_default_config(app_dir)
        print("Создана папка configs с шаблоном конфига")
    
    for file in os.listdir(configs_dir):
        if file.endswith(".py") and not file.startswith("__"):
            configs.append(file[:-3])
    
    if not configs:
        create_default_config(app_dir)
        configs = ["config_template"]
        print("Создан шаблон конфига config_template.py")
    
    return configs

def create_default_config(app_dir: str) -> None:
    """Создание шаблона конфигурационного файла"""
    config_path = os.path.join(app_dir, "configs", "config_template.py")
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
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_template)

def load_settings(app_dir: str) -> Dict[str, Any]:
    """Загрузка настроек из файла"""
    settings_path = os.path.join(app_dir, 'configs', 'sh_profile.json')
    try:
        if os.path.exists(settings_path):
            with open(settings_path, 'r', encoding='utf-8') as f:
                loaded_settings = json.load(f)
                if loaded_settings.get('debug', False):
                    print(f"Настройки загружены из {settings_path}: {loaded_settings}")
                return loaded_settings
    except Exception as e:
        if loaded_settings.get('debug', False):
            print(f"Ошибка при загрузке настроек: {e}")
    return {}

def save_settings(app_dir: str, settings: Dict[str, Any]) -> None:
    """Сохранение настроек в файл"""
    try:
        settings_path = os.path.join(app_dir, 'sh_profile.json')
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        
        # Создаем копию настроек без API ключа
        settings_to_save = {
            'openai_model': settings.get('openai_model'),
            'system_prompt': settings.get('system_prompt'),
            'last_config': settings.get('last_config'),
            'available_models': settings.get('available_models', []),
            'debug': settings.get('debug', False),
            'max_dialogs': settings.get('max_dialogs', '100'),
            'max_messages': settings.get('max_messages', '100')
        }
        
        # Сохраняем состояние окна, если оно есть
        if 'window_state' in settings:
            settings_to_save['window_state'] = settings['window_state']
        
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings_to_save, f, ensure_ascii=False, indent=2)
        
        if settings.get('debug', False):
            print(f"Настройки сохранены в {settings_path}")
    except Exception as e:
        if settings.get('debug', False):
            print(f"Ошибка при сохранении настроек: {e}")
