import os
import json
import asyncio
import random
import re
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===== ФАЙЛЫ =====
COOKIES_FILE = "cookies.json"
ADS_FILE = "ads.json"
CONFIG_FILE = "config.json"
SENT_FILE = "sent.json"

# ===== КОНФИГ =====
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"delay": 10}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

def get_delay():
    return config.get('delay', 10)

def set_delay(value):
    config['delay'] = value
    save_config(config)

def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_sent(sent):
    with open(SENT_FILE, 'w', encoding='utf-8') as f:
        json.dump(sent, f, ensure_ascii=False, indent=2)

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

def get_data():
    return {
        "cookies": load_cookies(),
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
    except ValueError:
        title_idx = 1
        price_idx = 2
        ad_url_idx = 7
    result = []
    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) < max(title_idx, price_idx, ad_url_idx) + 1:
            continue
        result.append({
            'title': parts[title_idx] if title_idx < len(parts) else '',
            'price': parts[price_idx] if price_idx < len(parts) else '',
            'url': parts[ad_url_idx] if ad_url_idx < len(parts) else ''
        })
    return result

def extract_ad_id_from_url(url):
    if not url:
        return None
    match = re.search(r'-([A-Za-z0-9]+)\.html$', url)
    if match:
        return match.group(1)
    return None

def extract_price(price_str):
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d]', '', price_str)
    if cleaned and cleaned.isdigit():
        return int(cleaned)
    return None

# ===== ОТПРАВКА =====
def send_message_via_api(ad_url, message_text):
    """Отправляет сообщение через API используя куки"""
    
    ad_id = extract_ad_id_from_url(ad_url)
    if not ad_id:
        return {"error": "Не удалось извлечь ID"}
    
    cookies_list = load_cookies()
    if not cookies_list:
        return {"error": "Нет кук!"}
    
    cookies_dict = {}
    for c in cookies_list:
        cookies_dict[c['name']] = c['value']
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Accept-Language": "ro,en;q=0.9",
        "Content-Type": "application/json",
        "Version": "2.0"
    }
    
    try:
        session = requests.Session()
        session.cookies.update(cookies_dict)
        
        response = session.post(
            f"https://www.olx.ro/api/partner/ads/{ad_id}/threads",
            headers=headers,
            json={"message": {"text": message_text}},
            timeout=30
        )
        
        if response.status_code == 201:
            return {"success": True}
        
        if response.status_code == 409:
            threads = session.get(
                f"https://www.olx.ro/api/partner/ads/{ad_id}/threads",
                headers=headers,
                timeout=30
            )
            if threads.status_code == 200:
                thread_data = threads.json()
                if thread_data and len(thread_data) > 0:
                    thread_id = thread_data[0].get('id')
                    if thread_id:
                        msg_response = session.post(
                            f"https://www.olx.ro/api/partner/threads/{thread_id}/messages",
                            headers=headers,
                            json={"text": message_text},
                            timeout=30
                        )
                        if msg_response.status_code == 201:
                            return {"success": True}
            return {"error": "Не удалось найти чат"}
        
        if response.status_code == 404:
            return {"error": "Объявление снято с публикации"}
        
        return {"error": f"Ошибка {response.status_code}"}
        
    except Exception as e:
        return {"error": str(e)}

# ===== АВТО-РАССЫЛКА =====
async def auto_send_messages(context, chat_id, ads, message_text):
    sent = load_sent()
    total = len(ads)
    success = 0
    errors = []
    
    for i, ad in enumerate(ads):
        # Пропускаем уже отправленные
        if ad['url'] in sent:
            continue
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ {i+1}/{total}: {ad.get('title', '')[:30]}..."
        )
        
        result = send_message_via_api(ad['url'], message_text)
        
        if result.get('success'):
            success += 1
            sent.append(ad['url'])
            save_sent(sent)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ {i+1}/{total}: {ad.get('title', '')[:30]} — отправлено!"
            )
        else:
            errors.append(f"{ad.get('title', '')[:30]}: {result.get('error', 'Ошибка')}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ {i+1}/{total}: {ad.get('title', '')[:30]}\n{result.get('error', 'Ошибка')}"
            )
        
        await asyncio.sleep(get_delay())
    
    report = f"✅ РАССЫЛКА ЗАВЕРШЕНА!\n\n📦 Всего: {total}\n✅ Отправлено: {success}\n❌ Ошибок: {len(errors)}"
    return report

# ===== КЛАВИАТУРЫ =====
def main_menu():
    d = get_data()
    status_cookies = "✅" if d['cookies'] else "⬜️"
    status_ads = "✅" if d['ads'] else "⬜️"
    
    keyboard = [
        [InlineKeyboardButton(f"🍪 Куки {status_cookies}", callback_data="cookies_menu")],
        [InlineKeyboardButton(f"📦 Объявления {status_ads}", callback_data="ads_menu")],
        [InlineKeyboardButton("⚙️ НАСТРОЙКИ", callback_data="settings_menu")],
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton("🚀 ЗАПУСТИТЬ РАССЫЛКУ", callback_data="start_auto_send")],
        [InlineKeyboardButton("🗑️ Сбросить отправленные", callback_data="reset_sent")],
        [InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 OLX AUTO SENDER\n\n"
        "🚀 АВТОМАТИЧЕСКАЯ РАССЫЛКА!\n\n"
        "1️⃣ Загрузите куки\n"
        "2️⃣ Загрузите CSV с объявлениями\n"
        "3️⃣ Напишите текст сообщения\n"
        "4️⃣ Нажмите «Запустить рассылку»\n\n"
        "✅ Бот запоминает отправленные объявления!",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "main_menu":
        await query.edit_message_text("📋 Главное меню", parse_mode='HTML', reply_markup=main_menu())
        return

    if data == "stats":
        d = get_data()
        sent = load_sent()
        msg = (
            f"📊 СТАТИСТИКА\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🍪 Куки: {'✅' if d['cookies'] else '⬜️'} ({len(d['cookies'])} шт.)\n"
            f"📦 Объявления: {'✅' if d['ads'] else '⬜️'} ({len(d['ads'])} шт.)\n"
            f"✅ Отправлено: {len(sent)}\n"
            f"⏱ Задержка: {get_delay()} сек"
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "help":
        await query.edit_message_text(
            "❓ ПОМОЩЬ\n\n"
            "📌 Как получить куки:\n"
            "1. Установите расширение EditThisCookie\n"
            "2. Зайдите на olx.ro и войдите\n"
            "3. Нажмите расширение → Export\n"
            "4. Скопируйте JSON и отправьте боту\n\n"
            "📌 CSV формат:\n"
            "title,price,ad_url\n\n"
            "📌 Текст сообщения:\n"
            "Просто напишите текст в чат",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    if data == "reset_sent":
        save_sent([])
        await query.edit_message_text("✅ Список отправленных очищен!", reply_markup=main_menu())
        return

    if data == "cookies_menu":
        keyboard = [
            [InlineKeyboardButton("📤 Загрузить куки (файл)", callback_data="upload_cookies_file")],
            [InlineKeyboardButton("📝 Загрузить куки (текст)", callback_data="upload_cookies_text")],
            [InlineKeyboardButton("🗑️ Удалить куки", callback_data="clear_cookies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        d = get_data()
        await query.edit_message_text(
            f"🍪 КУКИ\n\nСтатус: {'✅ Загружены' if d['cookies'] else '⬜️ Не загружены'}\nКоличество: {len(d['cookies'])} шт.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "upload_cookies_file":
        await query.edit_message_text("📤 Отправьте файл с куками (JSON-массив)", reply_markup=back_button())
        context.user_data['action'] = 'upload_cookies'
        return

    if data == "upload_cookies_text":
        await query.edit_message_text("📝 Отправьте JSON с куками", reply_markup=back_button())
        context.user_data['action'] = 'upload_cookies'
        return

    if data == "clear_cookies":
        save_cookies([])
        await query.edit_message_text("✅ Куки удалены!", reply_markup=main_menu())
        return

    if data == "ads_menu":
        keyboard = [
            [InlineKeyboardButton("📤 Загрузить CSV", callback_data="upload_csv")],
            [InlineKeyboardButton("📋 Список объявлений", callback_data="list_ads")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_ads")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        d = get_data()
        await query.edit_message_text(
            f"📦 ОБЪЯВЛЕНИЯ\n\nВсего: {len(d['ads'])} шт.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "upload_csv":
        await query.edit_message_text("📤 Отправьте CSV-файл", reply_markup=back_button())
        context.user_data['action'] = 'upload_csv'
        return

    if data == "list_ads":
        d = get_data()
        if not d['ads']:
            await query.edit_message_text("❌ Нет объявлений.", reply_markup=back_button())
            return
        sent = load_sent()
        msg = "📋 ОБЪЯВЛЕНИЯ\n\n"
        for i, ad in enumerate(d['ads'][:20]):
            status = "✅" if ad['url'] in sent else "⬜️"
            msg += f"{i+1}. {status} {ad.get('title', '')[:40]}\n"
        if len(d['ads']) > 20:
            msg += f"\n... и ещё {len(d['ads']) - 20}"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_ads":
        save_ads([])
        await query.edit_message_text("✅ Объявления удалены!", reply_markup=main_menu())
        return

    if data == "settings_menu":
        keyboard = [
            [InlineKeyboardButton(f"⏱ Задержка: {get_delay()} сек", callback_data="delay_menu")],
            [InlineKeyboardButton("🗑️ ОЧИСТИТЬ ВСЁ", callback_data="clear_all")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text("⚙️ НАСТРОЙКИ", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "delay_menu":
        keyboard = [
            [InlineKeyboardButton("5 сек", callback_data="delay_5")],
            [InlineKeyboardButton("10 сек", callback_data="delay_10")],
            [InlineKeyboardButton("15 сек", callback_data="delay_15")],
            [InlineKeyboardButton("20 сек", callback_data="delay_20")],
            [InlineKeyboardButton("30 сек", callback_data="delay_30")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
        ]
        await query.edit_message_text(f"⏱ ВЫБЕРИТЕ ЗАДЕРЖКУ\n\nТекущая: {get_delay()} сек", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("delay_"):
        seconds = int(data.split("_")[1])
        set_delay(seconds)
        await query.edit_message_text(f"✅ Задержка: {seconds} сек", reply_markup=main_menu())
        return

    if data == "clear_all":
        save_cookies([])
        save_ads([])
        save_sent([])
        await query.edit_message_text("🔄 ВСЕ ДАННЫЕ ОЧИЩЕНЫ!", parse_mode='HTML', reply_markup=main_menu())
        return

    if data == "start_auto_send":
        ads = load_ads()
        if not ads:
            await query.edit_message_text("❌ Нет объявлений!", reply_markup=back_button())
            return
        
        cookies = load_cookies()
        if not cookies:
            await query.edit_message_text("❌ Нет кук!", reply_markup=back_button())
            return
        
        message_text = context.user_data.get('message_text')
        if not message_text:
            await query.edit_message_text(
                "📝 Сначала напишите текст сообщения в чат!",
                reply_markup=back_button()
            )
            return
        
        sent = load_sent()
        remaining = [ad for ad in ads if ad['url'] not in sent]
        
        if not remaining:
            await query.edit_message_text(
                "✅ Все объявления уже отправлены!\nНажмите «Сбросить отправленные» для повторной рассылки.",
                reply_markup=main_menu()
            )
            return
        
        await query.edit_message_text(
            f"🚀 ЗАПУСК РАССЫЛКИ!\n\n"
            f"📦 Всего: {len(ads)}\n"
            f"✅ Отправлено: {len(sent)}\n"
            f"⏳ Осталось: {len(remaining)}\n"
            f"⏱ Задержка: {get_delay()} сек\n\n"
            f"⏳ Начинаю...",
            parse_mode='HTML'
        )
        
        report = await auto_send_messages(context, query.from_user.id, remaining, message_text)
        await context.bot.send_message(chat_id=query.from_user.id, text=report, parse_mode='HTML', reply_markup=main_menu())
        return

# ===== ОБРАБОТЧИКИ ФАЙЛОВ =====
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    file_name = document.file_name.lower()
    file = await document.get_file()
    content = await file.download_as_bytearray()
    text = content.decode('utf-8').strip()

    try:
        cookies = json.loads(text)
        if isinstance(cookies, list) and len(cookies) > 0:
            save_cookies(cookies)
            await update.message.reply_text(f"✅ КУКИ ЗАГРУЖЕНЫ!\n\n{len(cookies)} шт.", parse_mode='HTML', reply_markup=main_menu())
            return
    except:
        pass

    if file_name.endswith('.csv'):
        parsed = parse_csv_text(text)
        if parsed:
            save_ads(parsed)
            await update.message.reply_text(f"✅ CSV ЗАГРУЖЕН!\n\n{len(parsed)} объявлений", parse_mode='HTML', reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Ошибка парсинга CSV", reply_markup=back_button())
        return

    await update.message.reply_text(f"⚠️ Неизвестный файл: {file_name}", reply_markup=back_button())

# ===== ОБРАБОТЧИК ТЕКСТА =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    text = update.message.text.strip()

    if not action:
        context.user_data['message_text'] = text
        await update.message.reply_text(
            f"✅ Текст сохранён!\n\n📝 {text[:200]}{'...' if len(text) > 200 else ''}\n\n"
            f"Теперь нажмите «🚀 ЗАПУСТИТЬ РАССЫЛКУ»",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        return

    if action == 'upload_cookies':
        try:
            cookies = json.loads(text)
            if isinstance(cookies, list) and len(cookies) > 0:
                save_cookies(cookies)
                await update.message.reply_text(f"✅ КУКИ ЗАГРУЖЕНЫ!\n\n{len(cookies)} шт.", parse_mode='HTML', reply_markup=main_menu())
            else:
                await update.message.reply_text("❌ Неверный формат", reply_markup=back_button())
        except:
            await update.message.reply_text("❌ Неверный JSON", reply_markup=back_button())
        user_data['action'] = None
        return

    if action == 'upload_csv':
        await update.message.reply_text("❌ Отправьте CSV-файл", reply_markup=back_button())
        user_data['action'] = None
        return

# ===== ЗАПУСК =====
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not found!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    random.seed()
    main()
