import os
import csv
import json
import asyncio
import random
import requests
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===== ФАЙЛЫ ДЛЯ ХРАНЕНИЯ =====
TOKENS_FILE = "tokens.txt"
PROXIES_FILE = "proxies.txt"
TEXTS_FILE = "texts.txt"
ADS_FILE = "ads.json"
DELAY_FILE = "delay.txt"

# ===== ЗАГРУЗКА ДАННЫХ =====
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

def load_delay():
    if os.path.exists(DELAY_FILE):
        with open(DELAY_FILE, 'r', encoding='utf-8') as f:
            try:
                return int(f.read().strip())
            except:
                return 5
    return 5

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

def save_delay(delay):
    with open(DELAY_FILE, 'w', encoding='utf-8') as f:
        f.write(str(delay))

# ===== ГЛОБАЛЬНЫЕ ДАННЫЕ =====
tokens = load_tokens()
proxies = load_proxies()
texts = load_texts()
ads = load_ads()
delay = load_delay()

# ===== КЛАВИАТУРЫ =====
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("👤 Токены", callback_data="accounts_menu")],
        [InlineKeyboardButton("🌐 Прокси", callback_data="proxies_menu")],
        [InlineKeyboardButton("📝 Тексты", callback_data="texts_menu")],
        [InlineKeyboardButton("⏱ Задержка", callback_data="delay_menu")],
        [InlineKeyboardButton("📤 CSV", callback_data="upload_csv")],
        [InlineKeyboardButton("🚀 Рассылка", callback_data="start_send")],
        [InlineKeyboardButton("🔄 Очистить", callback_data="clear_all")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])

# ===== ФУНКЦИИ =====
def extract_ad_id_from_url(url):
    if not url:
        return None
    match = re.search(r'-([A-Za-z0-9]+)\.html$', url)
    if match:
        return match.group(1)
    return None

def get_account_name(access_token):
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    try:
        response = requests.get(
            "https://www.olx.ro/api/partner/users/me",
            headers=headers,
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('display_name') or data.get('name') or data.get('email', 'Без имени')
        return "Без имени"
    except:
        return "Без имени"

def send_message_via_api(access_token, ad_id, message_text, proxy=None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    proxies = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}
    try:
        session = requests.Session()
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
        return {"error": f"Ошибка {response.status_code}: {response.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>OLX Рассыльщик</b>\n\n"
        "📌 Команды:\n"
        "/add_token <токен> - добавить токен\n"
        "/add_proxy <прокси> - добавить прокси\n"
        "/add_text <текст> - добавить текст\n"
        "/list - показать всё\n"
        "/clear - очистить всё\n"
        "/menu - открыть меню",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 <b>Меню</b>", parse_mode='HTML', reply_markup=main_menu())

async def add_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Используйте: /add_token <ваш_токен>")
        return
    token = context.args[0]
    name = get_account_name(token)
    tokens.append(token)
    save_tokens(tokens)
    await update.message.reply_text(
        f"✅ <b>Токен добавлен!</b>\n\n👤 {name}\n🔑 <code>{token[:15]}...{token[-10:]}</code>\n\nВсего: {len(tokens)}",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

async def add_proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Используйте: /add_proxy http://user:pass@ip:port")
        return
    proxy = context.args[0]
    proxies.append(proxy)
    save_proxies(proxies)
    await update.message.reply_text(f"✅ Прокси добавлен!\n\nВсего: {len(proxies)}", reply_markup=main_menu())

async def add_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Используйте: /add_text <текст>")
        return
    text = ' '.join(context.args)
    texts.append(text)
    save_texts(texts)
    await update.message.reply_text(f"✅ Текст добавлен!\n\nВсего: {len(texts)}", reply_markup=main_menu())

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"📊 <b>Статистика</b>\n\n"
    msg += f"👤 Токенов: {len(tokens)}\n"
    msg += f"🌐 Прокси: {len(proxies)}\n"
    msg += f"📝 Текстов: {len(texts)}\n"
    msg += f"📦 Объявлений: {len(ads)}\n"
    msg += f"⏱ Задержка: {delay} сек"
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=main_menu())

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tokens.clear()
    proxies.clear()
    texts.clear()
    ads.clear()
    save_tokens(tokens)
    save_proxies(proxies)
    save_texts(texts)
    save_ads(ads)
    await update.message.reply_text("🔄 <b>Всё очищено!</b>", parse_mode='HTML', reply_markup=main_menu())

# ===== КНОПКИ (CallbackQuery) =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "main_menu":
        await query.edit_message_text("📋 <b>Меню</b>", parse_mode='HTML', reply_markup=main_menu())
        return
    
    elif query.data == "stats":
        msg = f"📊 <b>Статистика</b>\n\n"
        msg += f"👤 Токенов: {len(tokens)}\n"
        msg += f"🌐 Прокси: {len(proxies)}\n"
        msg += f"📝 Текстов: {len(texts)}\n"
        msg += f"📦 Объявлений: {len(ads)}\n"
        msg += f"⏱ Задержка: {delay} сек"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return
    
    elif query.data == "accounts_menu":
        keyboard = [
            [InlineKeyboardButton("📋 Список", callback_data="list_accounts")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_tokens")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"👤 <b>Токены</b>\n\nВсего: {len(tokens)}\n\nЧтобы добавить — /add_token <токен>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "list_accounts":
        if not tokens:
            await query.edit_message_text("❌ Нет токенов.", reply_markup=back_button())
            return
        msg = "📋 <b>Токены</b>\n\n"
        for i, t in enumerate(tokens):
            name = get_account_name(t)
            msg += f"{i+1}. {name}\n   <code>{t[:15]}...{t[-10:]}</code>\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return
    
    elif query.data == "clear_tokens":
        tokens.clear()
        save_tokens(tokens)
        await query.edit_message_text("✅ Токены удалены!", reply_markup=back_button())
        return
    
    elif query.data == "proxies_menu":
        keyboard = [
            [InlineKeyboardButton("📋 Список", callback_data="list_proxies")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_proxies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🌐 <b>Прокси</b>\n\nВсего: {len(proxies)}\n\nЧтобы добавить — /add_proxy http://user:pass@ip:port",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "list_proxies":
        if not proxies:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        msg = "📋 <b>Прокси</b>\n\n"
        for i, p in enumerate(proxies):
            clean = re.sub(r':[^:@]+@', ':****@', p)
            msg += f"{i+1}. <code>{clean}</code>\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return
    
    elif query.data == "clear_proxies":
        proxies.clear()
        save_proxies(proxies)
        await query.edit_message_text("✅ Прокси удалены!", reply_markup=back_button())
        return
    
    elif query.data == "texts_menu":
        keyboard = [
            [InlineKeyboardButton("📋 Список", callback_data="list_texts")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_texts")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"📝 <b>Тексты</b>\n\nВсего: {len(texts)}\n\nЧтобы добавить — /add_text <текст>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "list_texts":
        if not texts:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        msg = "📋 <b>Тексты</b>\n\n"
        for i, t in enumerate(texts):
            msg += f"{i+1}. {t[:100]}{'...' if len(t) > 100 else ''}\n\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return
    
    elif query.data == "clear_texts":
        texts.clear()
        save_texts(texts)
        await query.edit_message_text("✅ Тексты удалены!", reply_markup=back_button())
        return
    
    elif query.data == "delay_menu":
        keyboard = [
            [InlineKeyboardButton("1 сек", callback_data="delay_1")],
            [InlineKeyboardButton("3 сек", callback_data="delay_3")],
            [InlineKeyboardButton("5 сек", callback_data="delay_5")],
            [InlineKeyboardButton("10 сек", callback_data="delay_10")],
            [InlineKeyboardButton("15 сек", callback_data="delay_15")],
            [InlineKeyboardButton("30 сек", callback_data="delay_30")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"⏱ <b>Задержка</b>\n\nТекущая: {delay} сек",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data.startswith("delay_"):
        global delay
        delay = int(query.data.split("_")[1])
        save_delay(delay)
        await query.edit_message_text(f"✅ Задержка: {delay} сек", reply_markup=main_menu())
        return
    
    elif query.data == "upload_csv":
        await query.edit_message_text(
            "📤 <b>Загрузка CSV</b>\n\nОтправьте CSV-файл с объявлениями.\n\nФормат:\n<code>country,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return
    
    elif query.data == "start_send":
        if not tokens or not texts or not ads:
            errors = []
            if not tokens: errors.append("❌ Нет токенов")
            if not texts: errors.append("❌ Нет текстов")
            if not ads: errors.append("❌ Нет объявлений")
            await query.edit_message_text("⚠️ " + "\n".join(errors), reply_markup=back_button())
            return
        
        await query.edit_message_text(
            f"🚀 <b>Рассылка начата!</b>\n\n"
            f"👤 Токенов: {len(tokens)}\n"
            f"🌐 Прокси: {len(proxies)}\n"
            f"📦 Объявлений: {len(ads)}\n"
            f"📝 Текстов: {len(texts)}\n"
            f"⏱ Задержка: {delay} сек",
            parse_mode='HTML'
        )
        
        result = await send_all_messages(context, query.from_user.id)
        await context.bot.send_message(chat_id=query.from_user.id, text=result, parse_mode='HTML', reply_markup=main_menu())
        return
    
    elif query.data == "clear_all":
        tokens.clear()
        proxies.clear()
        texts.clear()
        ads.clear()
        save_tokens(tokens)
        save_proxies(proxies)
        save_texts(texts)
        save_ads(ads)
        await query.edit_message_text("🔄 <b>Всё очищено!</b>", parse_mode='HTML', reply_markup=main_menu())
        return

# ===== РАССЫЛКА =====
async def send_all_messages(context, chat_id) -> str:
    total = len(ads)
    sent = 0
    errors = []
    
    for i, ad in enumerate(ads, 1):
        try:
            token = random.choice(tokens)
            proxy = random.choice(proxies) if proxies else None
            text_template = random.choice(texts)
            
            ad_id = extract_ad_id_from_url(ad.get('url', ''))
            if not ad_id:
                errors.append(f"{i}. {ad.get('title', '')[:30]}: не найден ID")
                continue
            
            message_text = text_template.format(
                title=ad.get('title', 'Объявление'),
                price=ad.get('price', 'Цена не указана'),
                city=ad.get('city', ''),
                description=ad.get('description', '')[:300],
                url=ad.get('url', '#')
            )
            
            result = send_message_via_api(token, ad_id, message_text, proxy)
            if result.get('success'):
                sent += 1
            else:
                errors.append(f"{i}. {ad.get('title', '')[:30]}: {result.get('error', 'Ошибка')}")
            
            if i < total:
                await asyncio.sleep(delay)
            
            if i % 5 == 0:
                await context.bot.send_message(chat_id=chat_id, text=f"⏳ Прогресс: {i}/{total}")
        except Exception as e:
            errors.append(f"{i}. {str(e)}")
    
    report = f"✅ <b>Рассылка завершена!</b>\n\n"
    report += f"📦 Всего: {total}\n"
    report += f"✅ Отправлено: {sent}\n"
    report += f"❌ Ошибок: {len(errors)}\n"
    report += f"⏱ Задержка: {delay} сек\n\n"
    if errors:
        report += "📋 <b>Ошибки:</b>\n"
        for err in errors[:10]:
            report += f"- {err}\n"
        if len(errors) > 10:
            report += f"... и ещё {len(errors) - 10} ошибок\n"
    return report

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

# ===== ОБРАБОТЧИК СООБЩЕНИЙ =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Используйте команды:\n"
        "/add_token <токен>\n"
        "/add_proxy <прокси>\n"
        "/add_text <текст>\n"
        "/list\n"
        "/menu\n"
        "/clear",
        reply_markup=main_menu()
    )

async def handle_csv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.file_name.endswith('.csv'):
        await update.message.reply_text("⚠️ Отправьте CSV-файл.")
        return
    file = await document.get_file()
    content = await file.download_as_bytearray()
    try:
        text = content.decode('utf-8')
        parsed = parse_csv_text(text)
        if parsed:
            ads.clear()
            ads.extend(parsed)
            save_ads(ads)
            await update.message.reply_text(f"✅ CSV загружен! Объявлений: {len(ads)}", reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не удалось распарсить CSV.", reply_markup=back_button())
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ===== ЗАПУСК =====
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден!")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("add_token", add_token_command))
    app.add_handler(CommandHandler("add_proxy", add_proxy_command))
    app.add_handler(CommandHandler("add_text", add_text_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_csv_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    random.seed()
    main()
