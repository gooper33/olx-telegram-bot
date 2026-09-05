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
PROXIES_FILE = "proxies.txt"
TEXTS_FILE = "texts.txt"
ADS_FILE = "ads.json"
CONFIG_FILE = "config.json"

# ===== КОНФИГ =====
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"delay": 30}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

def get_delay():
    return config.get('delay', 30)

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

def load_proxies():
    if os.path.exists(PROXIES_FILE):
        with open(PROXIES_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def save_proxies(proxies):
    with open(PROXIES_FILE, 'w', encoding='utf-8') as f:
        for proxy in proxies:
            f.write(proxy + '\n')

def load_texts():
    if os.path.exists(TEXTS_FILE):
        with open(TEXTS_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

def save_texts(texts):
    with open(TEXTS_FILE, 'w', encoding='utf-8') as f:
        for text in texts:
            f.write(text + '\n')

def load_ads():
    if os.path.exists(ADS_FILE):
        with open(ADS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_ads(ads):
    with open(ADS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ads, f, ensure_ascii=False, indent=2)

def get_data():
    return {
        "cookies": load_cookies(),
        "proxies": load_proxies(),
        "texts": load_texts(),
        "ads": load_ads()
    }

# ===== ПАРСИНГ CSV =====
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
            'price': parts[price_idx] if price_idx < len(parts) else '',
            'url': parts[ad_url_idx] if ad_url_idx < len(parts) else '',
            'city': parts[city_idx] if city_idx < len(parts) else '',
            'description': parts[description_idx] if description_idx < len(parts) else ''
        })
    return result

# ===== ОТПРАВКА ЧЕРЕЗ PLAYWRIGHT (OLX.ro) =====
async def send_message_via_browser(ad_url, message_text, proxy=None):
    """Отправляет сообщение через браузер — эмуляция реального пользователя на OLX.ro"""
    
    async with async_playwright() as p:
        browser_options = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080",
                "--lang=ro-RO"
            ]
        }
        
        if proxy:
            browser_options["proxy"] = {"server": proxy}
        
        try:
            browser = await p.chromium.launch(**browser_options)
        except Exception as e:
            return {"error": f"Не удалось запустить браузер: {str(e)}"}
        
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
            return {"error": "❌ Нет cookies для авторизации"}
        
        page = await context.new_page()
        
        try:
            await page.goto(ad_url, timeout=60000, wait_until="domcontentloaded")
            
            # Случайная задержка
            await asyncio.sleep(random.uniform(2, 4))
            
            # Проверка авторизации
            if await page.locator('button[data-testid="login-button"]').count() > 0:
                await browser.close()
                return {"error": "❌ Не авторизован на OLX.ro"}
            
            # Ищем кнопку "Scrie" на OLX.ro
            write_button = None
            selectors = [
                'button:has-text("Scrie")',
                'button:has-text("Mesaj")',
                'button:has-text("Trimite mesaj")',
                'button:has-text("Contactează")',
                'a:has-text("Scrie")',
                'button[data-testid="send-message-button"]',
                'button.css-1x3m8a0'  # OLX.ro специфичный класс
            ]
            
            for selector in selectors:
                if await page.locator(selector).count() > 0:
                    write_button = page.locator(selector).first
                    break
            
            if not write_button:
                await browser.close()
                return {"error": "❌ Кнопка 'Scrie' не найдена"}
            
            await write_button.click()
            await asyncio.sleep(random.uniform(1.5, 3))
            
            # Ищем поле ввода на OLX.ro
            textarea = None
            textarea_selectors = [
                'textarea',
                '[contenteditable="true"]',
                'div[role="textbox"]',
                'textarea[placeholder*="Scrie"]',
                'textarea[placeholder*="Mesaj"]',
                'textarea.css-1x3m8a0'
            ]
            
            for selector in textarea_selectors:
                if await page.locator(selector).count() > 0:
                    textarea = page.locator(selector).first
                    break
            
            if not textarea:
                await browser.close()
                return {"error": "❌ Поле ввода не найдено"}
            
            await textarea.click()
            await asyncio.sleep(0.5)
            
            # Печатаем текст с задержкой
            for char in message_text:
                await page.keyboard.type(char, delay=random.randint(20, 60))
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Ищем кнопку отправки на OLX.ro
            send_button = None
            send_selectors = [
                'button:has-text("Trimite")',
                'button[type="submit"]',
                'button:has-text("Send")',
                'button:has-text("Trimite mesaj")',
                'button.css-1x3m8a0'
            ]
            
            for selector in send_selectors:
                if await page.locator(selector).count() > 0:
                    send_button = page.locator(selector).first
                    break
            
            if not send_button:
                await browser.close()
                return {"error": "❌ Кнопка отправки не найдена"}
            
            await send_button.click()
            await asyncio.sleep(random.uniform(3, 5))
            
            await page.close()
            await browser.close()
            
            return {"success": True}
            
        except Exception as e:
            await browser.close()
            return {"error": f"❌ {str(e)}"}

# ===== КЛАВИАТУРЫ =====
def main_menu():
    d = get_data()
    status_cookies = "✅" if d['cookies'] else "⬜️"
    status_proxies = "✅" if d['proxies'] else "⬜️"
    status_texts = "✅" if d['texts'] else "⬜️"
    status_ads = "✅" if d['ads'] else "⬜️"
    
    keyboard = [
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton(f"🍪 Куки {status_cookies}", callback_data="cookies_menu")],
        [InlineKeyboardButton(f"🌐 Прокси {status_proxies}", callback_data="proxies_menu")],
        [InlineKeyboardButton(f"📝 Тексты {status_texts}", callback_data="texts_menu")],
        [InlineKeyboardButton(f"📦 Объявления {status_ads}", callback_data="ads_menu")],
        [InlineKeyboardButton("⚙️ НАСТРОЙКИ", callback_data="settings_menu")],
        [InlineKeyboardButton("🚀 ЗАПУСТИТЬ РАССЫЛКУ", callback_data="start_send")],
        [InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])

def confirm_button():
    keyboard = [
        [InlineKeyboardButton("✅ ДА, ОТПРАВИТЬ", callback_data="confirm_send")],
        [InlineKeyboardButton("❌ ОТМЕНА", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>OLX Sender Pro</b>\n\n"
        "📌 <b>Бот для массовой рассылки на OLX.ro</b>\n\n"
        "✅ Работает как реальный человек через браузер\n"
        "✅ Может писать первым в любые объявления\n\n"
        "⬇️ Используйте кнопки ниже для управления",
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
        progress = 0
        if d['cookies']: progress += 25
        if d['proxies']: progress += 10
        if d['texts']: progress += 25
        if d['ads']: progress += 40
        ready = d['cookies'] and d['texts'] and d['ads']
        
        bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
        
        msg = (
            f"📊 <b>СТАТИСТИКА</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🍪 Куки: {'✅ Загружены' if d['cookies'] else '⬜️ Не загружены'} ({len(d['cookies'])} шт.)\n"
            f"🌐 Прокси: {'✅ Загружены' if d['proxies'] else '⬜️ Не загружены'} ({len(d['proxies'])} шт.)\n"
            f"📝 Тексты: {'✅ Загружены' if d['texts'] else '⬜️ Не загружены'} ({len(d['texts'])} шт.)\n"
            f"📦 Объявления: {'✅ Загружены' if d['ads'] else '⬜️ Не загружены'} ({len(d['ads'])} шт.)\n"
            f"⏱ Задержка: {get_delay()} сек\n\n"
            f"📊 Готовность: {progress}%\n"
            f"┌{'─' * 12}┐\n"
            f"│ {bar} │\n"
            f"└{'─' * 12}┘\n\n"
            f"{'✅ ГОТОВ К РАССЫЛКЕ' if ready else '⬜️ ЗАГРУЗИТЕ ВСЕ ДАННЫЕ'}"
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "help":
        await query.edit_message_text(
            "❓ <b>ПОМОЩЬ</b>\n\n"
            "📌 <b>Как получить куки:</b>\n"
            "1. Установите расширение «EditThisCookie»\n"
            "2. Зайдите на olx.ro и войдите\n"
            "3. Нажмите расширение → Export\n"
            "4. Скопируйте JSON и отправьте боту\n\n"
            "📌 <b>Формат CSV:</b>\n"
            "country,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description\n\n"
            "📌 <b>Переменные в тексте:</b>\n"
            "{title} — название\n{price} — цена\n{city} — город\n{description} — описание\n{url} — ссылка",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    # ===== COOKIES =====
    if data == "cookies_menu":
        d = get_data()
        keyboard = [
            [InlineKeyboardButton("📤 Загрузить куки (файл)", callback_data="upload_cookies_file")],
            [InlineKeyboardButton("📝 Загрузить куки (текст)", callback_data="upload_cookies_text")],
            [InlineKeyboardButton("🗑️ Удалить куки", callback_data="clear_cookies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🍪 <b>УПРАВЛЕНИЕ КУКАМИ</b>\n\n"
            f"Статус: {'✅ Загружены' if d['cookies'] else '⬜️ Не загружены'}\n"
            f"Количество: {len(d['cookies'])} шт.\n\n"
            f"Куки нужны для авторизации на OLX.ro.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "upload_cookies_file":
        await query.edit_message_text(
            "📤 <b>Отправьте файл с куками</b>\n\n"
            "Файл может называться как угодно.\n"
            "Внутри должен быть JSON-массив.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'upload_cookies'
        return

    if data == "upload_cookies_text":
        await query.edit_message_text(
            "📝 <b>Отправьте JSON с куками</b>\n\n"
            "Пример: <code>[{\"name\":\"access_token\",\"value\":\"...\"}]</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'upload_cookies'
        return

    if data == "clear_cookies":
        save_cookies([])
        await query.edit_message_text("✅ Куки удалены!", reply_markup=main_menu())
        return

    # ===== ПРОКСИ =====
    if data == "proxies_menu":
        d = get_data()
        keyboard = [
            [InlineKeyboardButton("➕ Добавить прокси (текст)", callback_data="add_proxy")],
            [InlineKeyboardButton("📤 Загрузить файл прокси", callback_data="upload_proxies_file")],
            [InlineKeyboardButton("📋 Список прокси", callback_data="list_proxies")],
            [InlineKeyboardButton("🗑️ Удалить все прокси", callback_data="clear_proxies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🌐 <b>УПРАВЛЕНИЕ ПРОКСИ</b>\n\n"
            f"Всего: {len(d['proxies'])} шт.\n\n"
            f"Формат: <code>http://user:pass@ip:port</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "add_proxy":
        await query.edit_message_text(
            "✏️ <b>Отправьте прокси</b>\n\n"
            "Формат: <code>http://user:pass@ip:port</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'add_proxy'
        return

    if data == "upload_proxies_file":
        await query.edit_message_text(
            "📤 <b>Отправьте файл proxies.txt</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'upload_proxies_file'
        return

    if data == "list_proxies":
        d = get_data()
        if not d['proxies']:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        msg = "📋 <b>СПИСОК ПРОКСИ</b>\n\n"
        for i, p in enumerate(d['proxies']):
            clean = re.sub(r':[^:@]+@', ':****@', p)
            msg += f"{i+1}. <code>{clean}</code>\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_proxies":
        save_proxies([])
        await query.edit_message_text("✅ Прокси удалены!", reply_markup=main_menu())
        return

    # ===== ТЕКСТЫ =====
    if data == "texts_menu":
        d = get_data()
        keyboard = [
            [InlineKeyboardButton("➕ Добавить текст", callback_data="add_text")],
            [InlineKeyboardButton("📤 Загрузить файл текстов", callback_data="upload_texts_file")],
            [InlineKeyboardButton("📋 Список текстов", callback_data="list_texts")],
            [InlineKeyboardButton("🗑️ Удалить все тексты", callback_data="clear_texts")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"📝 <b>УПРАВЛЕНИЕ ТЕКСТАМИ</b>\n\n"
            f"Всего: {len(d['texts'])} шт.\n\n"
            f"Переменные:\n{{title}} — название\n{{price}} — цена\n{{city}} — город\n{{description}} — описание\n{{url}} — ссылка",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "add_text":
        await query.edit_message_text(
            "✏️ <b>Отправьте текст</b>\n\n"
            "Весь текст сохранится как одно сообщение.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'add_text'
        return

    if data == "upload_texts_file":
        await query.edit_message_text(
            "📤 <b>Отправьте файл texts.txt</b>\n\n"
            "Каждый текст с новой строки.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'upload_texts_file'
        return

    if data == "list_texts":
        d = get_data()
        if not d['texts']:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        msg = "📋 <b>СПИСОК ТЕКСТОВ</b>\n\n"
        for i, t in enumerate(d['texts']):
            msg += f"{i+1}. {t[:100]}{'...' if len(t) > 100 else ''}\n\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_texts":
        save_texts([])
        await query.edit_message_text("✅ Тексты удалены!", reply_markup=main_menu())
        return

    # ===== ОБЪЯВЛЕНИЯ =====
    if data == "ads_menu":
        d = get_data()
        keyboard = [
            [InlineKeyboardButton("📤 Загрузить CSV", callback_data="upload_csv")],
            [InlineKeyboardButton("📋 Список объявлений", callback_data="list_ads")],
            [InlineKeyboardButton("🗑️ Удалить все объявления", callback_data="clear_ads")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"📦 <b>УПРАВЛЕНИЕ ОБЪЯВЛЕНИЯМИ</b>\n\n"
            f"Всего: {len(d['ads'])} шт.\n\n"
            f"Формат CSV:\n"
            f"<code>country,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "upload_csv":
        await query.edit_message_text(
            "📤 <b>Отправьте CSV-файл</b>\n\n"
            "Формат: country,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'upload_csv'
        return

    if data == "list_ads":
        d = get_data()
        if not d['ads']:
            await query.edit_message_text("❌ Нет объявлений.", reply_markup=back_button())
            return
        msg = "📋 <b>СПИСОК ОБЪЯВЛЕНИЙ</b>\n\n"
        for i, ad in enumerate(d['ads'][:10]):
            msg += f"{i+1}. {ad.get('title', 'Без названия')[:50]}\n"
        if len(d['ads']) > 10:
            msg += f"\n... и ещё {len(d['ads']) - 10} объявлений"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_ads":
        save_ads([])
        await query.edit_message_text("✅ Объявления удалены!", reply_markup=main_menu())
        return

    # ===== НАСТРОЙКИ =====
    if data == "settings_menu":
        keyboard = [
            [InlineKeyboardButton(f"⏱ Задержка: {get_delay()} сек", callback_data="delay_menu")],
            [InlineKeyboardButton("🗑️ ОЧИСТИТЬ ВСЁ", callback_data="clear_all")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            "⚙️ <b>НАСТРОЙКИ</b>\n\n"
            f"⏱ Текущая задержка: <b>{get_delay()} сек</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "delay_menu":
        keyboard = [
            [InlineKeyboardButton("10 сек", callback_data="delay_10")],
            [InlineKeyboardButton("20 сек", callback_data="delay_20")],
            [InlineKeyboardButton("30 сек", callback_data="delay_30")],
            [InlineKeyboardButton("45 сек", callback_data="delay_45")],
            [InlineKeyboardButton("60 сек", callback_data="delay_60")],
            [InlineKeyboardButton("90 сек", callback_data="delay_90")],
            [InlineKeyboardButton("120 сек", callback_data="delay_120")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
        ]
        await query.edit_message_text(
            f"⏱ <b>ВЫБЕРИТЕ ЗАДЕРЖКУ</b>\n\n"
            f"Текущая: <b>{get_delay()} сек</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data.startswith("delay_"):
        seconds = int(data.split("_")[1])
        set_delay(seconds)
        await query.edit_message_text(f"✅ Задержка установлена: <b>{seconds} сек</b>", parse_mode='HTML', reply_markup=main_menu())
        return

    if data == "clear_all":
        save_cookies([])
        save_proxies([])
        save_texts([])
        save_ads([])
        await query.edit_message_text("🔄 <b>ВСЕ ДАННЫЕ ОЧИЩЕНЫ!</b>", parse_mode='HTML', reply_markup=main_menu())
        return

    # ===== РАССЫЛКА =====
    if data == "start_send":
        d = get_data()
        errors = []
        if not d['cookies']:
            errors.append("⬜️ Нет куки")
        if not d['texts']:
            errors.append("⬜️ Нет текстов")
        if not d['ads']:
            errors.append("⬜️ Нет объявлений")
        
        if errors:
            await query.edit_message_text(
                "⚠️ <b>НЕЛЬЗЯ НАЧАТЬ РАССЫЛКУ</b>\n\n" + "\n".join(errors),
                parse_mode='HTML',
                reply_markup=back_button()
            )
            return
        
        msg = (
            f"🚀 <b>ПОДТВЕРЖДЕНИЕ РАССЫЛКИ</b>\n\n"
            f"📦 Объявлений: {len(d['ads'])}\n"
            f"📝 Текстов: {len(d['texts'])}\n"
            f"🌐 Прокси: {len(d['proxies'])}\n"
            f"⏱ Задержка: {get_delay()} сек\n\n"
            f"⚠️ Бот будет работать как реальный человек.\n"
            f"На каждое объявление уйдёт ~30-60 секунд."
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=confirm_button())
        return

    if data == "confirm_send":
        await query.edit_message_text("🚀 <b>НАЧИНАЮ РАССЫЛКУ...</b>", parse_mode='HTML')
        d = get_data()
        result = await send_all_messages(context, query.from_user.id, d['proxies'], d['texts'], d['ads'])
        await context.bot.send_message(chat_id=query.from_user.id, text=result, parse_mode='HTML', reply_markup=main_menu())
        return

# ===== РАССЫЛКА =====
async def send_all_messages(context, chat_id, proxies, texts, ads) -> str:
    total = len(ads)
    sent = 0
    errors = []
    delay = get_delay()
    
    if total == 0:
        return "❌ Нет объявлений."
    
    start_time = datetime.now()
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📤 <b>НАЧИНАЮ ОБРАБОТКУ</b>\n\n📦 Всего: {total} объявлений\n⏱ Задержка: {delay} сек\n⏳ Это займёт ~{total * 45 // 60} минут",
        parse_mode='HTML'
    )
    
    for i, ad in enumerate(ads, 1):
        try:
            proxy = random.choice(proxies) if proxies else None
            text_template = random.choice(texts)
            
            message_text = text_template.format(
                title=ad.get('title', 'Объявление'),
                price=ad.get('price', 'Цена не указана'),
                city=ad.get('city', ''),
                description=ad.get('description', '')[:300],
                url=ad.get('url', '#')
            )
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏳ <b>{i}/{total}</b> {ad.get('title', '')[:40]}..."
            )
            
            result = await send_message_via_browser(ad['url'], message_text, proxy)
            
            if result.get('success'):
                sent += 1
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ <b>{i}/{total}</b> {ad.get('title', '')[:40]}\n└ Отправлено!"
                )
            else:
                error_msg = result.get('error', 'Ошибка')
                errors.append(f"{i}. {ad.get('title', '')[:30]}: {error_msg}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ <b>{i}/{total}</b> {ad.get('title', '')[:40]}\n└ {error_msg[:150]}"
                )
            
            if i < total:
                await asyncio.sleep(delay)
                
        except Exception as e:
            errors.append(f"{i}. {str(e)}")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    report = (
        f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА!</b>\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
        f"⏱ Время: {int(elapsed // 60)}м {int(elapsed % 60)}с\n\n"
        f"📦 Всего: <b>{total}</b>\n"
        f"✅ Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{len(errors)}</b>\n"
        f"⏱ Задержка: <b>{delay} сек</b>\n"
    )
    
    if errors:
        report += f"\n📋 <b>ОШИБКИ (первые 10):</b>\n"
        for err in errors[:10]:
            report += f"- {err}\n"
        if len(errors) > 10:
            report += f"... и ещё {len(errors) - 10} ошибок\n"
    
    return report

# ===== ОБРАБОТЧИК ФАЙЛОВ =====
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    file_name = document.file_name.lower()
    file = await document.get_file()
    content = await file.download_as_bytearray()
    
    try:
        text = content.decode('utf-8').strip()
    except:
        await update.message.reply_text("❌ Не удалось прочитать файл.", reply_markup=back_button())
        return

    # COOKIES
    try:
        cookies = json.loads(text)
        if isinstance(cookies, list) and len(cookies) > 0:
            save_cookies(cookies)
            await update.message.reply_text(
                f"✅ <b>КУКИ ЗАГРУЖЕНЫ!</b>\n\n"
                f"📦 Количество: <b>{len(cookies)}</b> шт.\n"
                f"👤 Аккаунтов: <b>1</b>",
                parse_mode='HTML',
                reply_markup=main_menu()
            )
            return
    except:
        pass

    # ПРОКСИ
    if "proxy" in file_name or file_name == "proxies.txt":
        proxies = [line.strip() for line in text.split('\n') if line.strip()]
        if proxies:
            save_proxies(proxies)
            await update.message.reply_text(f"✅ <b>ПРОКСИ ЗАГРУЖЕНЫ!</b>\n\n📦 Количество: {len(proxies)} шт.", parse_mode='HTML', reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не найдено прокси.", reply_markup=back_button())
        return

    # ТЕКСТЫ
    if "text" in file_name or file_name == "texts.txt":
        texts = [line.strip() for line in text.split('\n') if line.strip()]
        if texts:
            save_texts(texts)
            await update.message.reply_text(f"✅ <b>ТЕКСТЫ ЗАГРУЖЕНЫ!</b>\n\n📦 Количество: {len(texts)} шт.", parse_mode='HTML', reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не найдено текстов.", reply_markup=back_button())
        return

    # CSV
    if file_name.endswith('.csv'):
        parsed = parse_csv_text(text)
        if parsed:
            save_ads(parsed)
            await update.message.reply_text(f"✅ <b>CSV ЗАГРУЖЕН!</b>\n\n📦 Объявлений: <b>{len(parsed)}</b>", parse_mode='HTML', reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не удалось распарсить CSV.", reply_markup=back_button())
        return

    await update.message.reply_text(f"⚠️ Неизвестный файл: {file_name}", reply_markup=back_button())

# ===== ОБРАБОТЧИК ТЕКСТА =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    text = update.message.text.strip()

    if not action:
        await update.message.reply_text("Используйте меню для управления.", reply_markup=main_menu())
        return

    if action == 'upload_cookies':
        try:
            cookies = json.loads(text)
            if isinstance(cookies, list) and len(cookies) > 0:
                save_cookies(cookies)
                await update.message.reply_text(
                    f"✅ <b>КУКИ ЗАГРУЖЕНЫ!</b>\n\n"
                    f"📦 Количество: <b>{len(cookies)}</b> шт.\n"
                    f"👤 Аккаунтов: <b>1</b>",
                    parse_mode='HTML',
                    reply_markup=main_menu()
                )
            else:
                await update.message.reply_text("❌ Неверный формат.", reply_markup=back_button())
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Не удалось распарсить JSON.", reply_markup=back_button())
        user_data['action'] = None
        return

    if action == 'add_proxy':
        proxies = load_proxies()
        new_proxies = [p.strip() for p in text.split('\n') if p.strip()]
        proxies.extend(new_proxies)
        save_proxies(proxies)
        await update.message.reply_text(f"✅ <b>ПРОКСИ ДОБАВЛЕНЫ!</b>\n\n📦 Добавлено: {len(new_proxies)}\n📦 Всего: {len(proxies)}", parse_mode='HTML', reply_markup=main_menu())
        user_data['action'] = None
        return

    if action == 'upload_proxies_file':
        proxies = [p.strip() for p in text.split('\n') if p.strip()]
        if proxies:
            save_proxies(proxies)
            await update.message.reply_text(f"✅ <b>ПРОКСИ ЗАГРУЖЕНЫ!</b>\n\n📦 Количество: {len(proxies)} шт.", parse_mode='HTML', reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не найдено прокси.", reply_markup=back_button())
        user_data['action'] = None
        return

    if action == 'add_text':
        texts = load_texts()
        texts.append(text)
        save_texts(texts)
        await update.message.reply_text(
            f"✅ <b>ТЕКСТ ДОБАВЛЕН!</b>\n\n"
            f"📏 Длина: {len(text)} символов\n"
            f"📦 Всего: {len(texts)} шт.",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
        return

    if action == 'upload_texts_file':
        texts = [t.strip() for t in text.split('\n') if t.strip()]
        if texts:
            save_texts(texts)
            await update.message.reply_text(f"✅ <b>ТЕКСТЫ ЗАГРУЖЕНЫ!</b>\n\n📦 Количество: {len(texts)} шт.", parse_mode='HTML', reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не найдено текстов.", reply_markup=back_button())
        user_data['action'] = None
        return

    if action == 'upload_csv':
        await update.message.reply_text("❌ Отправьте CSV-файл.", reply_markup=back_button())
        user_data['action'] = None
        return

# ===== ЗАПУСК =====
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    random.seed()
    main()
