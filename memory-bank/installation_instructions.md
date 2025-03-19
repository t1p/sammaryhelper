# Инструкции по установке и запуску Sammaryhelper

## Установка и запуск
1. **Клонирование репозитория**
   - `git clone https://github.com/yourusername/sammaryhelper.git`
   - `cd sammaryhelper`
   
2. **Создание виртуального окружения**
   - `python -m venv venv`
   
3. **Активация виртуального окружения**
   - Для PowerShell:
     - `.\venv\Scripts\Activate.ps1`
   - Для cmd:
     - `venv\Scripts\activate.bat`
   
4. **Установка зависимостей**
   - `pip install -r requirements.txt`
   
5. **Запуск приложения**
   - `python -m Sammaryhelper.main`