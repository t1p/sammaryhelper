import os

# Создаем необходимые директории при инициализации пакета
app_dir = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(app_dir, 'configs'), exist_ok=True)
os.makedirs(os.path.join(app_dir, 'sessions'), exist_ok=True)
