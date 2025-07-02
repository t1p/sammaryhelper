@echo off
echo Активация виртуального окружения...
call .\venv\Scripts\activate.bat

IF %ERRORLEVEL% NEQ 0 (
    echo Ошибка активации виртуального окружения. Убедитесь, что venv создан.
    pause
    exit /b %ERRORLEVEL%
)

echo Запуск приложения Sammaryhelper...
python -m Sammaryhelper.main

IF %ERRORLEVEL% NEQ 0 (
    echo Приложение завершилось с ошибкой.
    pause
    exit /b %ERRORLEVEL%
)

echo Приложение Sammaryhelper завершило работу.
pause