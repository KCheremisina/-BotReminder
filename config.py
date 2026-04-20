
import json
import os
from datetime import datetime
from cicle import CyclicEventsScheduler

def load_config():
    """Загружает конфигурацию из JSON файла"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'messages_config.json')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return config
    except FileNotFoundError:
        print("Ошибка: файл messages_config.json не найден!")
        raise
    except json.JSONDecodeError as e:
        print(f"Ошибка в JSON файле: {e}")
        raise

CONFIG = load_config()

TOKEN = CONFIG['bot']['token']
CHAT_ID = CONFIG['bot']['chat_id']
USER_ID = CONFIG['bot'].get('user_id')

PROXY_URL = CONFIG['bot'].get('proxy_url')
PROXY_USERNAME = CONFIG['bot'].get('proxy_username')
PROXY_PASSWORD = CONFIG['bot'].get('proxy_password')
PROXY_TYPE = CONFIG['bot'].get('proxy_type', 'socks5')
MTPROTO_SECRET = CONFIG['bot'].get('mtproto_secret')

try:
    start_date_str = CONFIG['events']['start_date']
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    scheduler = CyclicEventsScheduler(start_date)
    print(f"✅ Планировщик событий инициализирован. Стартовая дата: {start_date_str}")
except KeyError:
    print("Ошибка: в конфигурации отсутствует секция events.start_date")
    start_date = datetime(2026, 2, 17)
    scheduler = CyclicEventsScheduler(start_date)
    print(f"⚠️ Используется дата по умолчанию: {start_date.strftime('%Y-%m-%d')}")

MESSAGES = CONFIG['messages']

__all__ = [
    'TOKEN', 'CHAT_ID', 'USER_ID', 'MESSAGES', 'scheduler', 
    'CONFIG', 'PROXY_URL', 'PROXY_USERNAME', 'PROXY_PASSWORD',
    'PROXY_TYPE', 'MTPROTO_SECRET'
]