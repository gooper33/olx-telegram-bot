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

# ===== ФАЙЛ ДЛЯ ХРАНЕНИЯ ДАННЫХ =====
DATA_FILE = "data.json"

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ =====
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "accounts": [],
        "proxies": [],
        "texts": [],
        "ads": [],
        "delay": 5
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# ===== КЛАВИАТУРЫ =====
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("👤 Управление токенами", callback_data="accounts_menu")],
        [InlineKeyboardButton("🌐 Управление прокси", callback_data="proxies_menu")],
        [InlineKeyboardButton("📝 Управление текстами", callback_data="texts_menu")],
        [InlineKeyboardButton("⏱ Задержка", callback_data="delay_menu")],
        [InlineKeyboardButton("📤 Загрузить CSV", callback_data="upload_csv")],
        [InlineKeyboardButton("🚀 Начать рассылку", callback_data="start_send")],
        [InlineKeyboardButton("🔄 Очистить всё", callback_data="clear_all")]
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

def get_account_name(access_token, proxy=None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    proxies = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}
    try:
        session = requests.Session()
        if proxies:
            session.proxies.update(proxies)
        response = session.get(
            "https://www.olx.ro/api/partner/users/me",
            headers=headers,
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            name = data.get('display_name') or data.get('name') or data.get('email', 'Без имени')
            return name
        else:
            return f"Аккаунт {len(data['accounts']) + 1}"
    except Exception as e:
        return f"Аккаунт {len(data['accounts']) + 1}"

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
        "📌 Бот рассылает сообщения в чаты OLX\n\n"
        "1️⃣ Добавьте токены аккаунтов\n"
        "2️⃣ Добавьте прокси (необязательно)\n"
        "3️⃣ Загрузите CSV с объявлениями\n"
        "4️⃣ Добавьте тексты\n"
        "5️⃣ Начните рассылку",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "main_menu":
        await query.edit_message_text("👋 <b>Главное меню</b>", parse_mode='HTML', reply_markup=main_menu())
        return
    
    elif query.data == "stats":
        await query.edit_message_text(
            f"📊 <b>Статистика</b>\n\n"
            f"👤 Токенов: <b>{len(data['accounts'])}</b>\n"
            f"🌐 Прокси: <b>{len(data['proxies'])}</b>\n"
            f"📝 Текстов: <b>{len(data['texts'])}</b>\n"
            f"📦 Объявлений: <b>{len(data['ads'])}</b>\n"
            f"⏱ Задержка: <b>{data.get('delay', 5)} сек</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return
    
    elif query.data == "accounts_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить токен", callback_data="add_account")],
            [InlineKeyboardButton("📋 Список токенов", callback_data="list_accounts")],
            [InlineKeyboardButton("🗑️ Удалить токен", callback_data="delete_account")],
            [InlineKeyboardButton("🔄 Привязать прокси", callback_data="assign_proxies")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"👤 <b>Управление токенами</b>\n\nВсего: {len(data['accounts'])}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "add_account":
        context.user_data['action'] = 'add_account'
        await query.edit_message_text(
            "✏️ <b>Введите access_token</b>\n\nПросто отправьте токен в чат.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return
    
    elif query.data == "list_accounts":
        if not data['accounts']:
            await query.edit_message_text("❌ Нет токенов.", reply_markup=back_button())
            return
        text = ""
        for i, acc in enumerate(data['accounts']):
            token_short = acc['access_token'][:15] + "..." if len(acc['access_token']) > 20 else acc['access_token']
            proxy_status = "🌐" if acc.get('proxy') else "❌"
            name = acc.get('name', 'Без имени')
            text += f"{i+1}. {name} {proxy_status}\n   <code>{token_short}</code>\n"
        await query.edit_message_text(f"📋 <b>Токены</b>\n\n{text}", parse_mode='HTML', reply_markup=back_button())
        return
    
    elif query.data == "delete_account":
        if not data['accounts']:
            await query.edit_message_text("❌ Нет токенов.", reply_markup=back_button())
            return
        keyboard = []
        for i, acc in enumerate(data['accounts']):
            name = acc.get('name', f'Токен {i+1}')
            keyboard.append([InlineKeyboardButton(f"🗑️ {name}", callback_data=f"del_acc_{i}")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="accounts_menu")])
        await query.edit_message_text("🗑️ Выберите токен для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data.startswith("del_acc_"):
        idx = int(query.data.split("_")[2])
        data['accounts'].pop(idx)
        save_data(data)
        await query.edit_message_text(f"✅ Токен удалён. Осталось: {len(data['accounts'])}", reply_markup=back_button())
        return
    
    elif query.data == "assign_proxies":
        if not data['accounts']:
            await query.edit_message_text("❌ Нет токенов.", reply_markup=back_button())
            return
        if not data['proxies']:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        for i, acc in enumerate(data['accounts']):
            acc['proxy'] = data['proxies'][i % len(data['proxies'])]
        save_data(data)
        await query.edit_message_text(
            f"✅ Прокси привязаны!\n\nТокенов: {len(data['accounts'])}\nПрокси: {len(data['proxies'])}",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return
    
    elif query.data == "proxies_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить прокси", callback_data="add_proxies")],
            [InlineKeyboardButton("📋 Список прокси", callback_data="list_proxies")],
            [InlineKeyboardButton("🗑️ Удалить прокси", callback_data="delete_proxy")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🌐 <b>Управление прокси</b>\n\nВсего: {len(data['proxies'])}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "add_proxies":
        context.user_data['action'] = 'add_proxies'
        await query.edit_message_text(
            "🌐 <b>Введите прокси</b>\n\nКаждый с новой строки.\nФормат: http://user:pass@ip:port",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return
    
    elif query.data == "list_proxies":
        if not data['proxies']:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        text = ""
        for i, proxy in enumerate(data['proxies']):
            clean_proxy = re.sub(r':[^:@]+@', ':****@', proxy)
            text += f"{i+1}. <code>{clean_proxy}</code>\n"
        await query.edit_message_text(f"📋 <b>Прокси</b>\n\n{text}", parse_mode='HTML', reply_markup=back_button())
        return
    
    elif query.data == "delete_proxy":
        if not data['proxies']:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        keyboard = []
        for i, proxy in enumerate(data['proxies']):
            short = proxy[:30] + "..." if len(proxy) > 35 else proxy
            keyboard.append([InlineKeyboardButton(f"🗑️ {short}", callback_data=f"del_proxy_{i}")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="proxies_menu")])
        await query.edit_message_text("🗑️ Выберите прокси для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data.startswith("del_proxy_"):
        idx = int(query.data.split("_")[2])
        data['proxies'].pop(idx)
        save_data(data)
        await query.edit_message_text(f"✅ Прокси удалён. Осталось: {len(data['proxies'])}", reply_markup=back_button())
        return
    
    elif query.data == "texts_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить текст", callback_data="add_text")],
            [InlineKeyboardButton("📋 Список текстов", callback_data="list_texts")],
            [InlineKeyboardButton("🗑️ Удалить текст", callback_data="delete_text")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"📝 <b>Управление текстами</b>\n\nВсего: {len(data['texts'])}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "add_text":
        context.user_data['action'] = 'add_text'
        await query.edit_message_text(
            "📝 Отправьте текст для рассылки.\n\nПеременные:\n{title} - название\n{price} - цена\n{city} - город\n{description} - описание\n{url} - ссылка\n\nМожно несколько, разделяя ---",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return
    
    elif query.data == "list_texts":
        if not data['texts']:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        text = "\n\n---\n\n".join([f"{i+1}. {t[:100]}..." if len(t) > 100 else f"{i+1}. {t}" for i, t in enumerate(data['texts'])])
        await query.edit_message_text(f"📋 <b>Тексты</b>\n\n{text}", parse_mode='HTML', reply_markup=back_button())
        return
    
    elif query.data == "delete_text":
        if not data['texts']:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        keyboard = [[InlineKeyboardButton(f"🗑️ {t[:20]}...", callback_data=f"del_text_{i}")] for i, t in enumerate(data['texts'])]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="texts_menu")])
        await query.edit_message_text("🗑️ Выберите текст для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data.startswith("del_text_"):
        idx = int(query.data.split("_")[2])
        data['texts'].pop(idx)
        save_data(data)
        await query.edit_message_text(f"✅ Текст удалён. Осталось: {len(data['texts'])}", reply_markup=back_button())
        return
    
    elif query.data == "delay_menu":
        keyboard = [
            [InlineKeyboardButton("1 сек", callback_data="delay_1")],
            [InlineKeyboardButton("3 сек", callback_data="delay_3")],
            [InlineKeyboardButton("5 сек", callback_data="delay_5")],
            [InlineKeyboardButton("10 сек", callback_data="delay_10")],
            [InlineKeyboardButton("15 сек", callback_data="delay_15")],
            [InlineKeyboardButton("30 сек", callback_data="delay_30")],
            [InlineKeyboardButton("✏️ Своё", callback_data="delay_custom")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"⏱ <b>Задержка</b>\n\nТекущая: {data.get('delay', 5)} сек",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data.startswith("delay_"):
        if query.data == "delay_custom":
            context.user_data['action'] = 'set_delay'
            await query.edit_message_text("✏️ Введите задержку в секундах:", reply_markup=back_button())
        else:
            seconds = int(query.data.split("_")[1])
            data['delay'] = seconds
            save_data(data)
            await query.edit_message_text(f"✅ Задержка: {seconds} сек", reply_markup=main_menu())
        return
    
    elif query.data == "upload_csv":
        context.user_data['action'] = 'upload_csv'
        await query.edit_message_text(
            "📤 <b>Загрузка CSV</b>\n\nОтправьте CSV-файл с объявлениями.\n\nФормат:\ncountry,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description",
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return
    
    elif query.data == "start_send":
        errors = []
        if not data['accounts']:
            errors.append("❌ Нет токенов")
        if not data['texts']:
            errors.append("❌ Нет текстов")
        if not data['ads']:
            errors.append("❌ Нет объявлений")
        if errors:
            await query.edit_message_text(
                "⚠️ <b>Нельзя начать рассылку</b>\n\n" + "\n".join(errors),
                parse_mode='HTML',
                reply_markup=back_button()
            )
            return
        await query.edit_message_text(
            f"🚀 <b>Начинаю рассылку...</b>\n\n"
            f"👤 Токенов: {len(data['accounts'])}\n"
            f"🌐 Прокси: {len(data['proxies'])}\n"
            f"📦 Объявлений: {len(data['ads'])}\n"
            f"📝 Текстов: {len(data['texts'])}\n"
            f"⏱ Задержка: {data.get('delay', 5)} сек",
            parse_mode='HTML'
        )
        result = await send_all_messages(context, query.from_user.id)
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=result,
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        return
    
    elif query.data == "clear_all":
        data['accounts'] = []
        data['proxies'] = []
        data['texts'] = []
        data['ads'] = []
        data['delay'] = 5
        save_data(data)
        await query.edit_message_text("🔄 <b>Все данные очищены</b>", parse_mode='HTML', reply_markup=main_menu())
        return

# ===== ФУНКЦИЯ РАССЫЛКИ =====
async def send_all_messages(context, chat_id) -> str:
    ads = data['ads']
    texts = data['texts']
    accounts = data['accounts']
    delay = data.get('delay', 5)
    total = len(ads)
    sent = 0
    errors = []
    for i, ad in enumerate(ads, 1):
        try:
            account = random.choice(accounts)
            access_token = account['access_token']
            proxy = account.get('proxy')
            if not access_token:
                errors.append(f"❌ {account.get('name', 'без имени')}: пустой токен")
                continue
            ad_id = extract_ad_id_from_url(ad.get('url', ''))
            if not ad_id:
                errors.append(f"❌ {ad.get('title', 'Объявление')}: не удалось извлечь ID")
                continue
            text_template = random.choice(texts)
            message_text = text_template.format(
                title=ad.get('title', 'Объявление'),
                price=ad.get('price', 'Цена не указана'),
                city=ad.get('city', ''),
                description=ad.get('description', '')[:300],
                url=ad.get('url', '#')
            )
            result = send_message_via_api(access_token, ad_id, message_text, proxy)
            if result.get('success'):
                sent += 1
            else:
                errors.append(f"{i}. {ad.get('title', '')[:30]}: {result.get('error', 'Ошибка')}")
            if i < total:
                await asyncio.sleep(delay)
            if i % 5 == 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏳ Прогресс: {i}/{total} отправлено"
                )
        except Exception as e:
            errors.append(f"{i}. {str(e)}")
    report = f"✅ <b>Рассылка завершена!</b>\n\n"
    report += f"📦 Всего: <b>{total}</b>\n"
    report += f"✅ Отправлено: <b>{sent}</b>\n"
    report += f"❌ Ошибок: <b>{len(errors)}</b>\n"
    report += f"⏱ Задержка: <b>{delay} сек</b>\n\n"
    if errors:
        report += f"📋 <b>Ошибки (первые 10):</b>\n"
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
    ads = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) < max(title_idx, price_idx, ad_url_idx, city_idx, description_idx) + 1:
            continue
        ad_url = parts[ad_url_idx] if ad_url_idx < len(parts) else ''
        ads.append({
            'title': parts[title_idx] if title_idx < len(parts) else '',
            'price': parts[price_idx] if price_idx < len(parts) else '',
            'city': parts[city_idx] if city_idx < len(parts) else '',
            'description': parts[description_idx] if description_idx < len(parts) else '',
            'url': ad_url
        })
    return ads

# ===== ОБРАБОТЧИК СООБЩЕНИЙ =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    if not action:
        await update.message.reply_text("Используйте /start для открытия меню.", reply_markup=main_menu())
        return
    text = update.message.text.strip()
    if action == 'add_account':
        access_token = text
        name = get_account_name(access_token)
        account = {"access_token": access_token, "name": name, "proxy": None}
        data['accounts'].append(account)
        save_data(data)
        await update.message.reply_text(
            f"✅ <b>Токен добавлен!</b>\n\n👤 Имя: <b>{name}</b>\n🔑 <code>{access_token[:20]}...{access_token[-10:]}</code>\n\nВсего токенов: <b>{len(data['accounts'])}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
        return
    elif action == 'add_proxies':
        proxies = [p.strip() for p in text.split('\n') if p.strip()]
        data['proxies'].extend(proxies)
        save_data(data)
        await update.message.reply_text(
            f"✅ Добавлено прокси: <b>{len(proxies)}</b>\n\nВсего: <b>{len(data['proxies'])}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
        return
    elif action == 'add_text':
        if '---' in text:
            new_texts = [t.strip() for t in text.split('---') if t.strip()]
        else:
            new_texts = [text.strip()]
        data['texts'].extend(new_texts)
        save_data(data)
        await update.message.reply_text(
            f"✅ Добавлено текстов: <b>{len(new_texts)}</b>\n\nВсего: <b>{len(data['texts'])}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
        return
    elif action == 'upload_csv':
        try:
            ads = parse_csv_text(text)
            if ads:
                data['ads'] = ads
                save_data(data)
                await update.message.reply_text(
                    f"✅ Загружено объявлений: <b>{len(ads)}</b>",
                    parse_mode='HTML',
                    reply_markup=main_menu()
                )
            else:
                await update.message.reply_text("❌ Не удалось распарсить CSV.", reply_markup=back_button())
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        user_data['action'] = None
        return
    elif action == 'set_delay':
        try:
            seconds = int(text)
            if seconds < 1:
                await update.message.reply_text("❌ Задержка должна быть > 0")
                return
            data['delay'] = seconds
            save_data(data)
            await update.message.reply_text(f"✅ Задержка: {seconds} сек", reply_markup=main_menu())
        except ValueError:
            await update.message.reply_text("❌ Введите число")
        user_data['action'] = None
        return

async def handle_csv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.file_name.endswith('.csv'):
        await update.message.reply_text("⚠️ Отправьте файл в формате CSV.")
        return
    file = await document.get_file()
    content = await file.download_as_bytearray()
    try:
        text = content.decode('utf-8')
        ads = parse_csv_text(text)
        if ads:
            data['ads'] = ads
            save_data(data)
            await update.message.reply_text(
                f"✅ <b>CSV загружен!</b>\n\nОбъявлений: <b>{len(ads)}</b>",
                parse_mode='HTML',
                reply_markup=main_menu()
            )
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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_csv_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    random.seed()
    main()
