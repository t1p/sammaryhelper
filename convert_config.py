#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import importlib.util
import argparse

def convert_py_to_json(py_config_path):
    """
    Преобразует файл конфигурации из формата .py в формат .json
    
    Args:
        py_config_path (str): Путь к файлу .py
    
    Returns:
        bool: True если преобразование успешно, иначе False
    """
    try:
        # Получаем имя файла без расширения
        base_name = os.path.splitext(os.path.basename(py_config_path))[0]
        dir_path = os.path.dirname(py_config_path)
        json_config_path = os.path.join(dir_path, f"{base_name}.json")
        
        print(f"Конвертация файла {py_config_path} в {json_config_path}")
        
        # Загружаем Python-модуль
        spec = importlib.util.spec_from_file_location("config_module", py_config_path)
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)
        
        # Создаем словарь с настройками из модуля
        config_data = {
            "api_id": getattr(config_module, 'api_id', 0),
            "api_hash": getattr(config_module, 'api_hash', ""),
            "use_proxy": getattr(config_module, 'use_proxy', False),
            "openai_api_key": getattr(config_module, 'openai_api_key', "")
        }
        
        # Добавляем настройки прокси, если они есть
        if hasattr(config_module, 'proxy_settings'):
            config_data["proxy_settings"] = config_module.proxy_settings
        else:
            config_data["proxy_settings"] = {
                "proxy_type": "socks5",
                "proxy_host": "",
                "proxy_port": 0
            }
        
        # Добавляем настройки базы данных, если они есть
        if hasattr(config_module, 'db_settings'):
            config_data["db_settings"] = config_module.db_settings
        else:
            config_data["db_settings"] = {
                "host": "localhost",
                "port": 5432,
                "database": "telegram_summarizer",
                "user": "postgres",
                "password": "postgres"
            }
        
        # Сохраняем в JSON
        with open(json_config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        
        print(f"Файл успешно сконвертирован: {json_config_path}")
        return True
        
    except Exception as e:
        print(f"Ошибка при конвертации файла: {e}")
        return False

def main():
    # Создаем парсер аргументов командной строки
    parser = argparse.ArgumentParser(description='Конвертация конфига из формата .py в .json')
    parser.add_argument('config_file', help='Путь к файлу конфигурации .py')
    parser.add_argument('--all', action='store_true', help='Конвертировать все .py файлы в указанной директории')
    
    args = parser.parse_args()
    
    if args.all:
        # Если указан флаг --all, обрабатываем все .py файлы в директории
        dir_path = os.path.dirname(args.config_file) or '.'
        success_count = 0
        fail_count = 0
        
        for filename in os.listdir(dir_path):
            if filename.endswith('.py') and not filename.startswith('__'):
                full_path = os.path.join(dir_path, filename)
                if convert_py_to_json(full_path):
                    success_count += 1
                else:
                    fail_count += 1
        
        print(f"Конвертация завершена. Успешно: {success_count}, С ошибками: {fail_count}")
    else:
        # Иначе обрабатываем только указанный файл
        if not args.config_file.endswith('.py'):
            print("Ошибка: Указанный файл не является Python-файлом (.py)")
            sys.exit(1)
            
        if not os.path.exists(args.config_file):
            print(f"Ошибка: Файл не найден: {args.config_file}")
            sys.exit(1)
            
        if convert_py_to_json(args.config_file):
            print("Конвертация успешно завершена!")
        else:
            print("Конвертация завершилась с ошибками")
            sys.exit(1)

if __name__ == "__main__":
    main() 