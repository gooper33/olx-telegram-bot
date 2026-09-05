import os
import json
import asyncio
import random
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ===== ФАЙЛЫ =====
COOKIES_FILE = "cookies.json"
ADS_FILE = "ads.json"
TEXTS_FILE = "texts.txt"
CONFIG_FILE = "config.json"

# ===== КОНФИГ =====
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

# ===== ЗАГРУЗКА =====
def load_cookies():
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_cookies(cookies):
    with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)

def load_ads():
    if os.path.exists(ADS_FILE):
        with open(ADS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_ads(ads):
    with open(ADS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ads, f, ensure_ascii=False, indent=2)

def load_texts():
    if os.path.exists(TEXTS_FILE):
        with open(TEXTS_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def save_texts(texts):
    with open(TEXTS_FILE, 'w', encoding='utf-8') as f:
        for text in texts:
            f.write(text + '\n')

def get_data():
    return {
        "cookies": load_cookies(),
        "ads": load_ads(),
        "texts": load_texts()
    }

# ===== ПАРСИНГ CSV =====
def parse_csv_text(content: str) -> list:
    lines = content.strip().split('\n')
    if len(lines) < 2:
        return []
    header = lines[0].strip().split(',')
    try:
        title_idx = header.index('title')
        ad_url_idx = header.index('ad_url')
    except ValueError:
        return []
    result = []
    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) > max(title_idx, ad_url_idx):
            result.append({
                'title': parts[title_idx] if title_idx < len(parts) else '',
                'url': parts[ad_url_idx] if ad_url_idx < len(parts) else ''
            })
    return result

# ===== ОТПРАВКА ЧЕРЕЗ PLAYWRIGHT =====
async def send_message_via_browser(ad_url, message_text):
    """Отправляет сообщение через браузер — ВЫ сами ничего не делаете, бот всё делает автоматически!"""
    
    async with async_playwright() as p:
        browser_options = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080"
            ]
        }
        
        try:
            browser = await p.chromium.launch(**browser_options)
        except Exception as e:
            return {"error": f"❌ Браузер: {str(e)}"}
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ro-RO",
            timezone_id="Europe/Bucharest"
        )
        
        cookies = load_cookies()
        if cookies:
            await context.add_cookies(cookies)
        else:
            await browser.close()
            return {"error": "❌ Нет куки"}
        
        page = await context.new_page()
        
        try:
            await page.goto(ad_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))
            
            if await page.locator('button[data-testid="login-button"]').count() > 0:
                await browser.close()
                return {"error": "❌ Не авторизован"}
            
            write_button = None
            for selector in [
                'button:has-text("Scrie")',
                'button:has-text("Mesaj")',
                'button:has-text("Contactează")',
                'button[data-testid="send-message-button"]'
            ]:
                if await page.locator(selector).count() > 0:
                    write_button = page.locator(selector).first
                    break
            
            if not write_button:
                await browser.close()
                return {"error": "❌ Кнопка не найдена"}
            
            await write_button.click()
            await asyncio.sleep(random.uniform(1.5, 3))
            
            textarea = None
            for selector in ['textarea', '[contenteditable="true"]', 'div[role="textbox"]']:
                if await page.locator(selector).count() > 0:
                    textarea = page.locator(selector).first
                    break
            
            if not textarea:
                await browser.close()
                return {"error": "❌ Поле ввода не найдено"}
            
            await textarea.click()
            await asyncio.sleep(0.5)
            
            # Печатаем текст
            for char in message_text:
                await page.keyboard.type(char, delay=random.randint(20, 60))
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            send_button = None
            for selector in [
                'button:has-text("Trimite")',
                'button[type="submit"]'
            ]:
                if await page.locator(selector).count() > 0:
                    send_button = page.locator(selector).first
                    break
            
            if not send_button:
                await browser.close()
                return {"error": "❌ Кнопка отправки не найдена"}
            
            await send_button.click()
            await asyncio.sleep(random.uniform(3, 5))
            
            await browser.close()
            return {"success": True}
            
        except Exception as e:
            await browser.close()
            return {"error": f"❌ {str(e)}"}

# ===== КЛАВИАТУРЫ =====
def main_menu():
    d = get_data()
    status_cookies = "✅" if d['cookies'] else "⬜️"
    status_ads = "✅" if d['ads'] else "⬜️"
    status_texts = "✅" if d['texts'] else "⬜️"
    
    keyboard = [
        [InlineKeyboardButton(f"🍪 Куки {status_cookies}", callback_data="cookies_menu")],
        [InlineKeyboardButton(f"📦 Объявления {status_ads}", callback_data="ads_menu")],
        [InlineKeyboardButton(f"📝 Тексты {status_texts}", callback_data="texts_menu")],
        [InlineKeyboardButton("⚙️ НАСТРОЙКИ", callback_data="settings_menu")],
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton("🚀 ОТПРАВИТЬ СООБЩЕНИЕ", callback_data="send_message")],
        [InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])

def ads_list_menu():
    ads = load_ads()
    keyboard = []
    for i, ad in enumerate(ads[:30]):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {ad.get('title', '')[:35]}", callback_data=f"ad_{i}")])
    if not ads:
        keyboard.append([InlineKeyboardButton("❌ Нет объявлений", callback_data="main_menu")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def texts_list_menu():
    texts = load_texts()
    keyboard = []
    for i, t in enumerate(texts[:30]):
        short = t[:35] + "..." if len(t) > 35 else t
        keyboard.append([InlineKeyboardButton(f"{i+1}. {short}", callback_data=f"text_{i}")])
    if not texts:
        keyboard.append([InlineKeyboardButton("❌ Нет текстов", callback_data="main_menu")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>OLX Sender</b>\n\n"
        "📌 <b>Бот ОТПРАВЛЯЕТ сообщения за вас!</b>\n\n"
        "1️⃣ Загрузите куки\n"
        "2️⃣ Загрузите CSV с объявлениями\n"
        "3️⃣ Добавьте тексты\n"
        "4️⃣ Нажмите «Отправить сообщение»\n"
        "5️⃣ Выберите объявление и текст\n"
        "6️⃣ Бот САМ отправит сообщение!\n\n"
        "⬇️ Используйте кнопки ниже",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "main_menu":
        await query.edit_message_text("📋 <b>Главное меню</b>", parse_mode='HTML', reply_markup=main_menu())
        return

    if data == "stats":
        d = get_data()
        msg = (
            f"📊 <b>СТАТИСТИКА</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🍪 Куки: {'✅' if d['cookies'] else '⬜️'} ({len(d['cookies'])} шт.)\n"
            f"📦 Объявления: {'✅' if d['ads'] else '⬜️'} ({len(d['ads'])} шт.)\n"
            f"📝 Тексты: {'✅' if d['texts'] else '⬜️'} ({len(d['texts'])} шт.)\n"
            f"⏱ Задержка: {get_delay()} сек"
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "help":
        await query.edit_message_text(
            "❓ <b>ПОМОЩЬ</b>\n\n"
            "📌 <b>Как отправить сообщение:</b>\n"
            "1️⃣ Нажмите «Отправить сообщение»\n"
            "2️⃣ Выберите объявление\n"
            "3️⃣ Выберите текст\n"
            "4️⃣ Бот САМ отправит!\n\n"
            "📌 <b>Куки:</b> EditThisCookie → Export\n"
            "📌 <b>CSV:</b> title,ad_url",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    # ===== COOKIES =====
    if data == "cookies_menu":
        keyboard = [
            [InlineKeyboardButton("📤 Загрузить куки (файл)", callback_data="upload_cookies_file")],
            [InlineKeyboardButton("📝 Загрузить куки (текст)", callback_data="upload_cookies_text")],
            [InlineKeyboardButton("🗑️ Удалить куки", callback_data="clear_cookies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        d = get_data()
        await query.edit_message_text(
            f"🍪 <b>КУКИ</b>\n\n"
            f"Статус: {'✅ Загружены' if d['cookies'] else '⬜️ Не загружены'}\n"
            f"К
