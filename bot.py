import os
import json
import asyncio
import random
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# ===== ФАЙЛЫ ДЛЯ ХРАНЕНИЯ =====
COOKIES_FILE = "cookies.json"
PROXIES_FILE = "proxies.txt"
TEXTS_FILE = "texts.txt"
ADS_FILE = "ads.json"
CONFIG_FILE = "config.json"

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ КОНФИГА =====
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

# ===== ФУНКЦИЯ ОТПРАВКИ ЧЕРЕЗ PLAYWRIGHT =====
async def send_message_via_browser(ad_url, message_text, proxy=None):
    async with async_playwright() as p:
        browser_options = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"]
        }
        if proxy:
            browser_options["proxy"] = {"server": proxy}
        browser = await p.chromium.launch(**browser_options)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        cookies = load_cookies()
        if cookies:
            await context.add_cookies(cookies)
        else:
            await browser.close()
            return {"error": "Нет cookies"}
        page = await context.new_page()
        try:
            await page.goto(ad_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            if await page.locator('button[data-testid="login-button"]').count() > 0:
                await browser.close()
                return {"error": "Не авторизован"}
            write_button = None
            for selector in ['button:has-text("Scrie")', 'button:has-text("Mesaj")', 'a:has-text("Scrie")']:
                if await page.locator(selector).count() > 0:
                    write_button = page.locator(selector).first
                    break
            if not write_button:
                await browser.close()
                return {"error": "Кнопка не найдена"}
            await write_button.click()
            await asyncio.sleep(2)
            textarea = None
            for selector in ['textarea', '[contenteditable="true"]']:
                if await page.locator(selector).count() > 0:
                    textarea = page.locator(selector).first
                    break
            if not textarea:
                await browser.close()
                return {"error": "Поле ввода не найдено"}
            await textarea.fill(message_text)
            await asyncio.sleep(1)
            send_button = None
            for selector in ['button:has-text("Trimite")', 'button[type="submit"]']:
                if await page.locator(selector).count() > 0:
                    send_button = page.locator(selector).first
                    break
            if not send_button:
                await browser.close()
                return {"error": "Кнопка отправки не найдена"}
            await send_button.click()
            await asyncio.sleep(3)
            await browser.close()
            return {"success": True}
        except Exception as e:
            await browser.close()
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
        [InlineKeyboardButton("🍪 Cookies", callback_data="cookies_menu")],
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
        "📌 Команды:\n"
        "/addcookies - загрузить cookies\n"
        "/menu - открыть меню",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 <b>Меню</b>", parse_mode='HTML', reply_markup=main_menu())

async def add_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍪 <b>Отправьте JSON с cookies</b>\n\n"
        "1. Установите расширение «EditThisCookie»\n"
        "2. Зайдите на olx.ro и войдите в аккаунт\n"
        "3. Нажмите на расширение → Export\n"
        "4. Скопируйте ВЕСЬ JSON и отправьте сюда",
        parse_mode='HTML',
        reply_markup=back_button()
    )
    context.user_data['action'] = 'add_cookies'

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

    if data == "cookies_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Загрузить", callback_data="load_cookies")],
            [InlineKeyboardButton("🗑️ Удалить", callback_data="clear_cookies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        cookies_count = len(load_cookies())
        await query.edit_message_text(
            f"🍪 <b>Cookies</b>\n\nСтатус: <b>{'✅ Загружены' if cookies_count > 0 else '❌ Не загружены'}</b>\n"
            f"Количество: <b>{cookies_count}</b> шт.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "load_cookies":
        await query.edit_message_text(
            "🍪 Отправьте JSON с cookies\n\nИли используйте команду /addcookies",
            reply_markup=back_button()
        )
        context.user_data['action'] = 'add_cookies'
        return

    if data == "clear_cookies":
        save_cookies([])
        await query.edit_message_text("✅ Cookies удалены.", reply_markup=back_button())
        return

    if data == "proxies_menu":
        d = get_data()
        keyboard = [
            [InlineKeyboardButton("➕ Добавить", callback_data="add_proxy")],
            [InlineKeyboardButton("📋 Список", callback_data="list_proxies")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_proxies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(f"🌐 <b>Прокси</b>\n\nВсего: {len(d['proxies'])}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "add_proxy":
        context.user_data['action'] = 'add_proxy'
        await query.edit_message_text("✏️ Отправьте прокси:\n<code>http://user:pass@ip:port</code>", parse_mode='HTML', reply_markup=back_button())
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
            [InlineKeyboardButton("➕ Добавить", callback_data="add_text")],
            [InlineKeyboardButton("📋 Список", callback_data="list_texts")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_texts")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(f"📝 <b>Тексты</b>\n\nВсего: {len(d['texts'])}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "add_text":
        context.user_data['action'] = 'add_text'
        await query.edit_message_text(
            "✏️ Отправьте текст.\n\nПеременные:\n{title} — название\n{price} — цена\n{city} — город\n{description} — описание\n{url} — ссылка\n\nНесколько текстов разделяйте ---",
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
        context.user_data['action'] = 'upload_csv'
        await query.edit_message_text(
            "📤 <b>Загрузка CSV</b>\n\nОтправьте CSV-файл.\n\nФормат:\n<code>country,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    if data == "start_send":
        d = get_data()
        errors = []
        if not d['cookies']:
            errors.append("❌ Нет cookies (/addcookies)")
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
            f"⏱ Задержка: {get_delay()} сек\n\n⏳ Отправка...",
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
            result = await send_message_via_browser(ad['url'], message_text, proxy)
            if result.get('success'):
                sent += 1
                await context.bot.send_message(chat_id=chat_id, text=f"✅ {i}/{total}: {ad.get('title', '')[:30]} — отправлено!")
            else:
                errors.append(f"{i}. {ad.get('title', '')[:30]}: {result.get('error', 'Ошибка')}")
                await context.bot.send_message(chat_id=chat_id, text=f"❌ {i}/{total}: {ad.get('title', '')[:30]}\n{result.get('error', 'Ошибка')[:200]}")
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

# ===== ОБРАБОТЧИК СООБЩЕНИЙ =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    text = update.message.text.strip()

    if not action:
        await update.message.reply_text("Используйте /menu для открытия меню.", reply_markup=main_menu())
        return

    if action == 'add_cookies':
        try:
            cookies = json.loads(text)
            if isinstance(cookies, list) and len(cookies) > 0:
                save_cookies(cookies)
                await update.message.reply_text(
                    f"✅ <b>Cookies загружены!</b>\n\nКоличество: <b>{len(cookies)}</b> шт.",
                    parse_mode='HTML',
                    reply_markup=main_menu()
                )
            else:
                await update.message.reply_text("❌ Неверный формат.", reply_markup=back_button())
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Ошибка парсинга JSON.", reply_markup=back_button())
        user_data['action'] = None
        return

    if action == 'add_proxy':
        proxies = load_proxies()
        proxies.append(text)
        save_proxies(proxies)
        await update.message.reply_text(f"✅ Прокси добавлен!\nВсего: {len(proxies)}", reply_markup=main_menu())
        user_data['action'] = None
        return

    if action == 'add_text':
        texts = load_texts()
        if '---' in text:
            new_texts = [t.strip() for t in text.split('---') if t.strip()]
        else:
            new_texts = [text.strip()]
        texts.extend(new_texts)
        save_texts(texts)
        await update.message.reply_text(f"✅ Добавлено текстов: {len(new_texts)}\nВсего: {len(texts)}", reply_markup=main_menu())
        user_data['action'] = None
        return

    if action == 'upload_csv':
        await update.message.reply_text("❌ Отправьте CSV-файл.", reply_markup=back_button())
        user_data['action'] = None
        return

# ===== ОБРАБОТЧИК CSV =====
async def handle_csv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.file_name.endswith('.csv'):
        await update.message.reply_text("⚠️ Отправьте CSV-файл.", reply_markup=back_button())
        return
    file = await document.get_file()
    content = await file.download_as_bytearray()
    try:
        text = content.decode('utf-8')
        parsed = parse_csv_text(text)
        if parsed:
            save_ads(parsed)
            await update.message.reply_text(f"✅ CSV загружен! Объявлений: <b>{len(parsed)}</b>", parse_mode='HTML', reply_markup=main_menu())
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
    app.add_handler(CommandHandler("addcookies", add_cookies_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_csv_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    random.seed()
    main()
