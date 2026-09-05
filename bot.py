import os
import json
import asyncio
import random
import requests
import re
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

# ===== ГЛОБАЛЬНЫЕ ДАННЫЕ =====
tokens = load_tokens()
proxies = load_proxies()
texts = load_texts()
ads = load_ads()

# ===== ФУНКЦИИ =====
def extract_ad_id_from_url(url):
    if not url:
        return None
    match = re.search(r'-([A-Za-z0-9]+)\.html$', url)
    return match.group(1) if match else None

def get_account_name(access_token):
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    try:
        response = requests.get("https://www.olx.ro/api/partner/users/me", headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data.get('display_name') or data.get('name') or data.get('email', 'Без имени')
    except:
        pass
    return "Без имени"

def send_message_via_api(access_token, ad_id, message_text, proxy=None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
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
            threads = session.get(f"https://www.olx.ro/api/partner/ads/{ad_id}/threads", headers=headers, timeout=30)
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
        [InlineKeyboardButton("👤 Токены", callback_data="accounts_menu")],
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

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>OLX Рассыльщик</b>\n\n"
        "📌 Управляйте ботом через меню ниже.",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 <b>Меню</b>", parse_mode='HTML', reply_markup=main_menu())

# ===== ОСНОВНОЙ ОБРАБОТЧИК КНОПОК =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "main_menu":
        await query.edit_message_text("📋 <b>Главное меню</b>", parse_mode='HTML', reply_markup=main_menu())
        return

    # ===== СТАТИСТИКА =====
    if data == "stats":
        msg = (
            f"📊 <b>Статистика</b>\n\n"
            f"👤 Токенов: {len(tokens)}\n"
            f"🌐 Прокси: {len(proxies)}\n"
            f"📝 Текстов: {len(texts)}\n"
            f"📦 Объявлений: {len(ads)}\n"
            f"⏱ Задержка: {get_delay()} сек"
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    # ===== ТОКЕНЫ =====
    if data == "accounts_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить токен", callback_data="add_token")],
            [InlineKeyboardButton("📋 Список токенов", callback_data="list_tokens")],
            [InlineKeyboardButton("🗑️ Удалить все токены", callback_data="clear_tokens")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"👤 <b>Управление токенами</b>\n\nВсего: {len(tokens)}\n\nНажмите «Добавить токен» и отправьте токен в чат.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "add_token":
        context.user_data['action'] = 'add_token'
        await query.edit_message_text(
            "✏️ <b>Отправьте access_token</b>\n\nПросто вставьте токен и отправьте в чат.\n\nИмя аккаунта будет получено автоматически.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    if data == "list_tokens":
        if not tokens:
            await query.edit_message_text("❌ Нет токенов.", reply_markup=back_button())
            return
        msg = "📋 <b>Токены</b>\n\n"
        for i, t in enumerate(tokens):
            name = get_account_name(t)
            msg += f"{i+1}. {name}\n   <code>{t[:15]}...{t[-10:]}</code>\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_tokens":
        tokens.clear()
        save_tokens(tokens)
        await query.edit_message_text("✅ Все токены удалены.", reply_markup=back_button())
        return

    # ===== ПРОКСИ =====
    if data == "proxies_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить прокси", callback_data="add_proxy")],
            [InlineKeyboardButton("📋 Список прокси", callback_data="list_proxies")],
            [InlineKeyboardButton("🗑️ Удалить все прокси", callback_data="clear_proxies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🌐 <b>Управление прокси</b>\n\nВсего: {len(proxies)}\n\nНажмите «Добавить прокси» и отправьте прокси в чат.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "add_proxy":
        context.user_data['action'] = 'add_proxy'
        await query.edit_message_text(
            "✏️ <b>Отправьте прокси</b>\n\nФормат: <code>http://user:pass@ip:port</code>\n\nМожно отправить несколько — каждый с новой строки.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    if data == "list_proxies":
        if not proxies:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        msg = "📋 <b>Прокси</b>\n\n"
        for i, p in enumerate(proxies):
            clean = re.sub(r':[^:@]+@', ':****@', p)
            msg += f"{i+1}. <code>{clean}</code>\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_proxies":
        proxies.clear()
        save_proxies(proxies)
        await query.edit_message_text("✅ Все прокси удалены.", reply_markup=back_button())
        return

    # ===== ТЕКСТЫ =====
    if data == "texts_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить текст", callback_data="add_text")],
            [InlineKeyboardButton("📋 Список текстов", callback_data="list_texts")],
            [InlineKeyboardButton("🗑️ Удалить все тексты", callback_data="clear_texts")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"📝 <b>Управление текстами</b>\n\nВсего: {len(texts)}\n\nНажмите «Добавить текст» и отправьте текст в чат.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "add_text":
        context.user_data['action'] = 'add_text'
        await query.edit_message_text(
            "✏️ <b>Отправьте текст</b>\n\nПеременные:\n<code>{title}</code> — название\n<code>{price}</code> — цена\n<code>{city}</code> — город\n<code>{description}</code> — описание\n<code>{url}</code> — ссылка\n\nМожно отправить несколько — разделяйте их <code>---</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    if data == "list_texts":
        if not texts:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        msg = "📋 <b>Тексты</b>\n\n"
        for i, t in enumerate(texts):
            msg += f"{i+1}. {t[:100]}{'...' if len(t) > 100 else ''}\n\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_texts":
        texts.clear()
        save_texts(texts)
        await query.edit_message_text("✅ Все тексты удалены.", reply_markup=back_button())
        return

    # ===== ЗАДЕРЖКА =====
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
        await query.edit_message_text(
            f"⏱ <b>Задержка между сообщениями</b>\n\nТекущая: {get_delay()} сек",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data.startswith("delay_"):
        seconds = int(data.split("_")[1])
        set_delay(seconds)
        await query.edit_message_text(f"✅ Задержка установлена: {seconds} сек", reply_markup=main_menu())
        return

    # ===== CSV =====
    if data == "upload_csv":
        context.user_data['action'] = 'upload_csv'
        await query.edit_message_text(
            "📤 <b>Загрузка CSV</b>\n\nОтправьте CSV-файл с объявлениями.\n\nФормат:\n<code>country,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    # ===== РАССЫЛКА =====
    if data == "start_send":
        errors = []
        if not tokens:
            errors.append("❌ Нет токенов")
        if not texts:
            errors.append("❌ Нет текстов")
        if not ads:
            errors.append("❌ Нет объявлений (загрузите CSV)")

        if errors:
            await query.edit_message_text("⚠️ " + "\n".join(errors), parse_mode='HTML', reply_markup=back_button())
            return

        await query.edit_message_text(
            f"🚀 <b>Начинаю рассылку...</b>\n\n"
            f"👤 Токенов: {len(tokens)}\n"
            f"🌐 Прокси: {len(proxies)}\n"
            f"📦 Объявлений: {len(ads)}\n"
            f"📝 Текстов: {len(texts)}\n"
            f"⏱ Задержка: {get_delay()} сек",
            parse_mode='HTML'
        )

        result = await send_all_messages(context, query.from_user.id)
        await context.bot.send_message(chat_id=query.from_user.id, text=result, parse_mode='HTML', reply_markup=main_menu())
        return

    # ===== ОЧИСТКА =====
    if data == "clear_all":
        tokens.clear()
        proxies.clear()
        texts.clear()
        ads.clear()
        save_tokens(tokens)
        save_proxies(proxies)
        save_texts(texts)
        save_ads(ads)
        await query.edit_message_text("🔄 <b>Все данные очищены!</b>", parse_mode='HTML', reply_markup=main_menu())
        return

# ===== РАССЫЛКА =====
async def send_all_messages(context, chat_id) -> str:
    total = len(ads)
    sent = 0
    errors = []
    delay = get_delay()

    for i, ad in enumerate(ads, 1):
        try:
            token = random.choice(tokens)
            proxy = random.choice(proxies) if proxies else None
            text_template = random.choice(texts)

            ad_id = extract_ad_id_from_url(ad.get('url', ''))
            if not ad_id:
                errors.append(f"{i}. {ad.get('title', '')[:30]}: ID не найден")
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

    report = (
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📦 Всего: {total}\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {len(errors)}\n"
        f"⏱ Задержка: {delay} сек\n\n"
    )
    if errors:
        report += "📋 <b>Ошибки:</b>\n"
        for err in errors[:10]:
            report += f"- {err}\n"
        if len(errors) > 10:
            report += f"... и ещё {len(errors) - 10} ошибок\n"
    return report

# ===== ОБРАБОТЧИК СООБЩЕНИЙ (ВВОД ОТ ПОЛЬЗОВАТЕЛЯ) =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    text = update.message.text.strip()

    if not action:
        await update.message.reply_text("Используйте кнопки меню.", reply_markup=main_menu())
        return

    if action == 'add_token':
        name = get_account_name(text)
        tokens.append(text)
        save_tokens(tokens)
        await update.message.reply_text(
            f"✅ <b>Токен добавлен!</b>\n\n👤 {name}\n🔑 <code>{text[:15]}...{text[-10:]}</code>\n\nВсего: {len(tokens)}",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
        return

    if action == 'add_proxy':
        new_proxies = [p.strip() for p in text.split('\n') if p.strip()]
        proxies.extend(new_proxies)
        save_proxies(proxies)
        await update.message.reply_text(
            f"✅ Добавлено прокси: {len(new_proxies)}\n\nВсего: {len(proxies)}",
            reply_markup=main_menu()
        )
        user_data['action'] = None
        return

    if action == 'add_text':
        if '---' in text:
            new_texts = [t.strip() for t in text.split('---') if t.strip()]
        else:
            new_texts = [text.strip()]
        texts.extend(new_texts)
        save_texts(texts)
        await update.message.reply_text(
            f"✅ Добавлено текстов: {len(new_texts)}\n\nВсего: {len(texts)}",
            reply_markup=main_menu()
        )
        user_data['action'] = None
        return

    if action == 'upload_csv':
        await update.message.reply_text("❌ Отправьте CSV-файл, а не текст.", reply_markup=back_button())
        user_data['action'] = None
        return

# ===== ОБРАБОТЧИК CSV-ФАЙЛОВ =====
async def handle_csv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.file_name.endswith('.csv'):
        await update.message.reply_text("⚠️ Отправьте файл в формате CSV.", reply_markup=back_button())
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
            await update.message.reply_text(
                f"✅ CSV загружен! Объявлений: {len(ads)}",
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text("❌ Не удалось распарсить CSV.", reply_markup=back_button())
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}", reply_markup=back_button())

# ===== ЗАПУСК =====
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_csv_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    random.seed()
    main()
