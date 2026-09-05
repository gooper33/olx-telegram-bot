import os
import json
import asyncio
import random
import re
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===== ФАЙЛЫ ДЛЯ ХРАНЕНИЯ =====
COOKIES_FILE = "cookies.json"
PROXIES_FILE = "proxies.txt"
TEXTS_FILE = "texts.txt"
ADS_FILE = "ads.json"
CONFIG_FILE = "config.json"

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ =====
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"delay": 15}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

def get_delay():
    return config.get('delay', 15)

def set_delay(value):
    config['delay'] = value
    save_config(config)

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

def get_data():
    return {
        "cookies": load_cookies(),
        "proxies": load_proxies(),
        "texts": load_texts(),
        "ads": load_ads()
    }

# ===== ОТПРАВКА ЧЕРЕЗ API =====
def send_message_via_api(ad_url, message_text, proxy=None):
    """Отправляет сообщение через OLX API с использованием cookies"""
    
    ad_id = None
    match = re.search(r'-([A-Za-z0-9]+)\.html$', ad_url)
    if match:
        ad_id = match.group(1)
    
    if not ad_id:
        return {"error": "Не удалось извлечь ID объявления"}
    
    cookies_list = load_cookies()
    cookies_dict = {}
    for c in cookies_list:
        cookies_dict[c['name']] = c['value']
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ro,en;q=0.9",
        "Content-Type": "application/json"
    }
    
    proxies = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}
    
    try:
        session = requests.Session()
        session.cookies.update(cookies_dict)
        if proxies:
            session.proxies.update(proxies)
        
        response = session.post(
            f"https://www.olx.ro/api/partner/ads/{ad_id}/threads",
            headers=headers,
            json={"message": {"text": message_text}},
            timeout=30
        )
        
        if response.status_code == 201:
            return {"success": True}
        elif response.status_code == 409:
            threads = session.get(
                f"https://www.olx.ro/api/partner/ads/{ad_id}/threads",
                headers=headers,
                timeout=30
            )
            if threads.status_code == 200:
                thread_data = threads.json()
                if thread_data.get('data') and len(thread_data['data']) > 0:
                    thread_id = thread_data['data'][0].get('id')
                    if thread_id:
                        msg_response = session.post(
                            f"https://www.olx.ro/api/partner/threads/{thread_id}/messages",
                            headers=headers,
                            json={"text": message_text},
                            timeout=30
                        )
                        if msg_response.status_code == 201:
                            return {"success": True}
                        else:
                            return {"error": f"Ошибка отправки: {msg_response.status_code}"}
            return {"error": "Не удалось найти чат"}
        else:
            return {"error": f"Ошибка {response.status_code}: {response.text[:200]}"}
            
    except Exception as e:
        return {"error": str(e)}

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

# ===== КЛАВИАТУРЫ =====
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🍪 Загрузить cookies", callback_data="upload_cookies")],
        [InlineKeyboardButton("🌐 Прокси", callback_data="proxies_menu")],
        [InlineKeyboardButton("📝 Тексты", callback_data="texts_menu")],
        [InlineKeyboardButton("⏱ Задержка", callback_data="delay_menu")],
        [InlineKeyboardButton("📤 Загрузить CSV", callback_data="upload_csv")],
        [InlineKeyboardButton("🚀 Начать рассылку", callback_data="start_send")],
        [InlineKeyboardButton("🔄 Очистить всё", callback_data="clear_all")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])

def stats_with_refresh():
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_stats")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>OLX Рассыльщик</b>\n\n"
        "📌 Как работать:\n"
        "1️⃣ Отправьте файл или текст с cookies\n"
        "2️⃣ Добавьте прокси через меню\n"
        "3️⃣ Отправьте CSV с объявлениями\n"
        "4️⃣ Добавьте тексты\n"
        "5️⃣ Начните рассылку",
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

    if data == "stats" or data == "refresh_stats":
        d = get_data()
        msg = (
            f"📊 <b>Статистика</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🍪 Cookies: <b>{'✅' if d['cookies'] else '❌'}</b>\n"
            f"🌐 Прокси: <b>{len(d['proxies'])}</b>\n"
            f"📝 Текстов: <b>{len(d['texts'])}</b>\n"
            f"📦 Объявлений: <b>{len(d['ads'])}</b>\n"
            f"⏱ Задержка: <b>{get_delay()} сек</b>"
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=stats_with_refresh())
        return

    if data == "upload_cookies":
        await query.edit_message_text(
            "🍪 <b>Загрузка cookies</b>\n\n"
            "Отправьте <b>файл</b> или просто <b>текст</b> с JSON-массивом.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'upload_cookies'
        return

    if data == "proxies_menu":
        d = get_data()
        keyboard = [
            [InlineKeyboardButton("➕ Добавить прокси", callback_data="add_proxy")],
            [InlineKeyboardButton("📋 Список", callback_data="list_proxies")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_proxies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(f"🌐 <b>Прокси</b>\n\nВсего: {len(d['proxies'])}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "add_proxy":
        context.user_data['action'] = 'add_proxy'
        await query.edit_message_text(
            "✏️ Отправьте прокси:\n<code>http://user:pass@ip:port</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    if data == "list_proxies":
        d = get_data()
        if not d['proxies']:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        msg = "📋 <b>Прокси</b>\n\n"
        for i, p in enumerate(d['proxies']):
            clean = re.sub(r':[^:@]+@', ':****@', p)
            msg += f"{i+1}. <code>{clean}</code>\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_proxies":
        save_proxies([])
        await query.edit_message_text("✅ Прокси удалены.", reply_markup=back_button())
        return

    if data == "texts_menu":
        d = get_data()
        keyboard = [
            [InlineKeyboardButton("➕ Добавить текст", callback_data="add_text")],
            [InlineKeyboardButton("📋 Список", callback_data="list_texts")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_texts")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(f"📝 <b>Тексты</b>\n\nВсего: {len(d['texts'])}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "add_text":
        context.user_data['action'] = 'add_text'
        await query.edit_message_text(
            "✏️ <b>Отправьте текст</b>\n\nПеременные:\n{title} — название\n{price} — цена\n{city} — город\n{description} — описание\n{url} — ссылка",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    if data == "list_texts":
        d = get_data()
        if not d['texts']:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        msg = "📋 <b>Тексты</b>\n\n"
        for i, t in enumerate(d['texts']):
            msg += f"{i+1}. {t[:100]}{'...' if len(t) > 100 else ''}\n\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_texts":
        save_texts([])
        await query.edit_message_text("✅ Тексты удалены.", reply_markup=back_button())
        return

    if data == "delay_menu":
        keyboard = [
            [InlineKeyboardButton("1 сек", callback_data="delay_1")],
            [InlineKeyboardButton("3 сек", callback_data="delay_3")],
            [InlineKeyboardButton("5 сек", callback_data="delay_5")],
            [InlineKeyboardButton("10 сек", callback_data="delay_10")],
            [InlineKeyboardButton("15 сек", callback_data="delay_15")],
            [InlineKeyboardButton("30 сек", callback_data="delay_30")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(f"⏱ <b>Задержка</b>\n\nТекущая: {get_delay()} сек", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("delay_"):
        seconds = int(data.split("_")[1])
        set_delay(seconds)
        await query.edit_message_text(f"✅ Задержка: {seconds} сек", reply_markup=main_menu())
        return

    if data == "upload_csv":
        await query.edit_message_text(
            "📤 <b>Загрузить CSV</b>\n\nОтправьте CSV-файл.\n\nФормат: country,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        context.user_data['action'] = 'upload_csv'
        return

    if data == "start_send":
        d = get_data()
        errors = []
        if not d['cookies']:
            errors.append("❌ Нет cookies")
        if not d['texts']:
            errors.append("❌ Нет текстов")
        if not d['ads']:
            errors.append("❌ Нет объявлений")
        if errors:
            await query.edit_message_text("⚠️ " + "\n".join(errors), parse_mode='HTML', reply_markup=back_button())
            return
        await query.edit_message_text(
            f"🚀 <b>Начинаю рассылку...</b>\n\n"
            f"🍪 Cookies: ✅\n🌐 Прокси: {len(d['proxies'])}\n"
            f"📦 Объявлений: {len(d['ads'])}\n📝 Текстов: {len(d['texts'])}\n"
            f"⏱ Задержка: {get_delay()} сек",
            parse_mode='HTML'
        )
        result = await send_all_messages(context, query.from_user.id, d['proxies'], d['texts'], d['ads'])
        await context.bot.send_message(chat_id=query.from_user.id, text=result, parse_mode='HTML', reply_markup=main_menu())
        return

    if data == "clear_all":
        save_cookies([])
        save_proxies([])
        save_texts([])
        save_ads([])
        await query.edit_message_text("🔄 <b>Все данные очищены!</b>", parse_mode='HTML', reply_markup=main_menu())
        return

# ===== РАССЫЛКА =====
async def send_all_messages(context, chat_id, proxies, texts, ads) -> str:
    total = len(ads)
    sent = 0
    errors = []
    delay = get_delay()
    
    if total == 0:
        return "❌ Нет объявлений."
    
    await context.bot.send_message(chat_id=chat_id, text=f"📤 Начинаю обработку {total} объявлений...")
    
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
            
            await context.bot.send_message(chat_id=chat_id, text=f"⏳ {i}/{total}: {ad.get('title', '')[:30]}...")
            
            result = send_message_via_api(ad['url'], message_text, proxy)
            
            if result.get('success'):
                sent += 1
                await context.bot.send_message(chat_id=chat_id, text=f"✅ {i}/{total}: {ad.get('title', '')[:30]} — отправлено!")
            else:
                error_msg = result.get('error', 'Ошибка')
                errors.append(f"{i}. {ad.get('title', '')[:30]}: {error_msg}")
                await context.bot.send_message(chat_id=chat_id, text=f"❌ {i}/{total}: {ad.get('title', '')[:30]}\n{error_msg[:200]}")
            
            if i < total:
                await asyncio.sleep(delay)
                
        except Exception as e:
            errors.append(f"{i}. {str(e)}")
    
    report = f"✅ <b>Рассылка завершена!</b>\n🕐 {datetime.now().strftime('%H:%M:%S')}\n\n📦 Всего: <b>{total}</b>\n✅ Отправлено: <b>{sent}</b>\n❌ Ошибок: <b>{len(errors)}</b>\n⏱ Задержка: <b>{delay} сек</b>\n"
    if errors:
        report += "\n📋 <b>Ошибки:</b>\n"
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

    try:
        cookies = json.loads(text)
        if isinstance(cookies, list) and len(cookies) > 0:
            save_cookies(cookies)
            await update.message.reply_text(
                f"✅ <b>Cookies загружены!</b>\n\n"
                f"Количество кук: <b>{len(cookies)}</b>\n"
                f"Аккаунтов: <b>1</b>",
                parse_mode='HTML',
                reply_markup=main_menu()
            )
            return
    except:
        pass

    if file_name == "proxies.txt":
        proxies = [line.strip() for line in text.split('\n') if line.strip()]
        if proxies:
            save_proxies(proxies)
            await update.message.reply_text(f"✅ Прокси загружены! {len(proxies)} шт.", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не найдено прокси.", reply_markup=back_button())
        return

    if file_name == "texts.txt":
        texts = [line.strip() for line in text.split('\n') if line.strip()]
        if texts:
            save_texts(texts)
            await update.message.reply_text(f"✅ Тексты загружены! {len(texts)} шт.", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не найдено текстов.", reply_markup=back_button())
        return

    if file_name.endswith('.csv'):
        parsed = parse_csv_text(text)
        if parsed:
            save_ads(parsed)
            await update.message.reply_text(f"✅ CSV загружен! Объявлений: {len(parsed)}", parse_mode='HTML', reply_markup=main_menu())
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
        await update.message.reply_text("Используйте /start или меню.", reply_markup=main_menu())
        return

    if action == 'upload_cookies':
        try:
            cookies = json.loads(text)
            if isinstance(cookies, list) and len(cookies) > 0:
                save_cookies(cookies)
                await update.message.reply_text(
                    f"✅ <b>Cookies загружены!</b>\n\n"
                    f"Количество кук: <b>{len(cookies)}</b>\n"
                    f"Аккаунтов: <b>1</b>",
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
        await update.message.reply_text(f"✅ Добавлено прокси: {len(new_proxies)}\nВсего: {len(proxies)}", reply_markup=main_menu())
        user_data['action'] = None
        return

    if action == 'add_text':
        texts = load_texts()
        texts.append(text)
        save_texts(texts)
        await update.message.reply_text(
            f"✅ <b>Текст добавлен!</b>\n\nДлина: {len(text)} символов\nВсего: {len(texts)}",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
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
