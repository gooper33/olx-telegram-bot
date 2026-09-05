import os
import json
import asyncio
import random
import requests
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===== ФАЙЛЫ ДЛЯ ХРАНЕНИЯ =====
TOKENS_FILE = "tokens.txt"
PROXIES_FILE = "proxies.txt"
TEXTS_FILE = "texts.txt"
ADS_FILE = "ads.json"
CONFIG_FILE = "config.json"

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ КОНФИГА =====
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"delay": 5}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

def get_delay():
    return config.get('delay', 5)

def set_delay(value):
    config['delay'] = value
    save_config(config)

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ =====
def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def load_proxies():
    if os.path.exists(PROXIES_FILE):
        with open(PROXIES_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def load_texts():
    if os.path.exists(TEXTS_FILE):
        with open(TEXTS_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def load_ads():
    if os.path.exists(ADS_FILE):
        with open(ADS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_tokens(tokens):
    with open(TOKENS_FILE, 'w', encoding='utf-8') as f:
        for token in tokens:
            f.write(token + '\n')

def save_proxies(proxies):
    with open(PROXIES_FILE, 'w', encoding='utf-8') as f:
        for proxy in proxies:
            f.write(proxy + '\n')

def save_texts(texts):
    with open(TEXTS_FILE, 'w', encoding='utf-8') as f:
        for text in texts:
            f.write(text + '\n')

def save_ads(ads):
    with open(ADS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ads, f, ensure_ascii=False, indent=2)

# ===== ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ СВЕЖИХ ДАННЫХ =====
def get_data():
    return {
        "tokens": load_tokens(),
        "proxies": load_proxies(),
        "texts": load_texts(),
        "ads": load_ads()
    }

# ===== ФУНКЦИИ =====
def extract_ad_id_from_url(url):
    if not url:
        return None
    match = re.search(r'-([A-Za-z0-9]+)\.html$', url)
    if match:
        return match.group(1)
    match = re.search(r'/([A-Za-z0-9]+)$', url)
    if match:
        return match.group(1)
    return None

def get_account_name(access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "x-api-version": "2.0"
    }
    try:
        response = requests.get("https://www.olx.ro/api/v2/users/me", headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data.get('display_name') or data.get('name') or data.get('email', 'Без имени')
    except:
        pass
    return "Без имени"

def send_message_via_api(access_token, ad_id, message_text, proxy=None):
    """Отправляет сообщение через OLX API v2 с созданием чата если нужно"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-api-version": "2.0"
    }
    
    proxies = {"http": proxy, "https": proxy} if proxy else None
    
    try:
        session = requests.Session()
        if proxies:
            session.proxies.update(proxies)
        
        # ШАГ 1: ПРОВЕРЯЕМ, ЕСТЬ ЛИ ЧАТ
        threads_response = session.get(
            f"https://www.olx.ro/api/v2/ads/{ad_id}/threads",
            headers=headers,
            timeout=30
        )
        
        print(f"📥 Чаты статус: {threads_response.status_code}")
        print(f"📥 Чаты ответ: {threads_response.text[:500]}")
        
        thread_id = None
        
        if threads_response.status_code == 200:
            thread_data = threads_response.json()
            threads_list = thread_data.get('data', [])
            if threads_list and len(threads_list) > 0:
                thread_id = threads_list[0].get('id')
                print(f"✅ Найден существующий чат: {thread_id}")
        
        # ШАГ 2: ЕСЛИ ЧАТА НЕТ — СОЗДАЁМ
        if not thread_id:
            print("🔁 Чата нет, создаём новый...")
            
            create_response = session.post(
                f"https://www.olx.ro/api/v2/ads/{ad_id}/threads",
                headers=headers,
                json={"message": {"text": message_text}},
                timeout=30
            )
            
            print(f"📥 Создание чата статус: {create_response.status_code}")
            print(f"📥 Создание чата ответ: {create_response.text[:500]}")
            
            if create_response.status_code == 201:
                return {"success": True}
            elif create_response.status_code == 409:
                threads_response2 = session.get(
                    f"https://www.olx.ro/api/v2/ads/{ad_id}/threads",
                    headers=headers,
                    timeout=30
                )
                if threads_response2.status_code == 200:
                    thread_data2 = threads_response2.json()
                    threads_list2 = thread_data2.get('data', [])
                    if threads_list2 and len(threads_list2) > 0:
                        thread_id = threads_list2[0].get('id')
                        if thread_id:
                            msg_response = session.post(
                                f"https://www.olx.ro/api/v2/threads/{thread_id}/messages",
                                headers=headers,
                                json={"text": message_text},
                                timeout=30
                            )
                            if msg_response.status_code == 201:
                                return {"success": True}
                            else:
                                return {"error": f"Ошибка отправки {msg_response.status_code}: {msg_response.text[:200]}"}
            else:
                return {"error": f"Ошибка создания чата {create_response.status_code}: {create_response.text[:200]}"}
        
        # ШАГ 3: ЕСЛИ ЧАТ ЕСТЬ — ОТПРАВЛЯЕМ
        if thread_id:
            print(f"📤 Отправка в чат {thread_id}")
            msg_response = session.post(
                f"https://www.olx.ro/api/v2/threads/{thread_id}/messages",
                headers=headers,
                json={"text": message_text},
                timeout=30
            )
            
            print(f"📥 Статус отправки: {msg_response.status_code}")
            print(f"📥 Ответ: {msg_response.text[:500]}")
            
            if msg_response.status_code == 201:
                return {"success": True}
            else:
                return {"error": f"Ошибка отправки {msg_response.status_code}: {msg_response.text[:200]}"}
        
        return {"error": "Не удалось создать или найти чат"}
            
    except requests.exceptions.Timeout:
        return {"error": "Таймаут соединения"}
    except requests.exceptions.ProxyError as e:
        return {"error": f"Ошибка прокси: {str(e)}"}
    except Exception as e:
        return {"error": f"Ошибка: {str(e)}"}

def parse_csv_text(content: str) -> list:
    lines = content.strip().split('\n')
    if len(lines) < 2:
        return []
    header = lines[0].strip().split(',')
    try:
        title_idx = header.index('title')
        price_idx = header.index('price')
        ad_url_idx = header.index('ad_url')
        city_idx = header.index('city')
        description_idx = header.index('description')
    except ValueError:
        return []
    result = []
    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) < max(title_idx, price_idx, ad_url_idx, city_idx, description_idx) + 1:
            continue
        result.append({
            'title': parts[title_idx] if title_idx < len(parts) else '',
            'price': parts[price
