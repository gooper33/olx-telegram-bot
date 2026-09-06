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
        price_idx = header.index('price')
        ad_url_idx = header.index('ad_url')
    except ValueError:
        return []
    result = []
    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) > max(title_idx, price_idx, ad_url_idx):
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
    """Извлекает число из строки с ценой"""
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d\s]', '', price_str)
    cleaned = cleaned.replace(' ', '')
    if cleaned and cleaned.isdigit():
        return int(cleaned)
    return None

# ===== ОТПРАВКА ПРЕДЛОЖЕНИЯ ЦЕНЫ (УНИВЕРСАЛЬНАЯ) =====
def send_offer_via_api(ad_url, offer_price, original_price):
    """
    Отправляет предложение цены через OLX API.
    Работает для ВСЕХ категорий!
    """
    ad_id = extract_ad_id_from_url(ad_url)
    
    if not ad_id:
        return {"error": "Не удалось извлечь ID объявления"}
    
    cookies_list = load_cookies()
    if not cookies_list:
        return {"error": "Нет кук. Загрузите куки через меню!"}
    
    cookies_dict = {}
    for c in cookies_list:
        cookies_dict[c['name']] = c['value']
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ro,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.olx.ro",
        "Referer": ad_url,
        "Version": "2.0"
    }
    
    payload = {
        "amount": offer_price,
        "currency": "RON",
        "message": f"Propun {offer_price} RON (prețul inițial: {original_price} RON)"
    }
    
    try:
        session = requests.Session()
        session.cookies.update(cookies_dict)
        
        # Сначала пробуем отправить официальный офер
        response = session.post(
            f"https://www.olx.ro/api/partner/ads/{ad_id}/offers",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        # Если офер не поддерживается (400 или 404) — отправляем сообщение в чат
        if response.status_code in [400, 404]:
            # Отправляем сообщение в чат вместо офера
            chat_response = session.post(
                f"https://www.olx.ro/api/partner/ads/{ad_id}/threads",
                headers=headers,
                json={"message": {"text": f"Bună ziua! Aș dori să vă fac o ofertă de {offer_price} RON pentru acest produs. Prețul dvs. este {original_price} RON. Vă rog să luați în considerare oferta mea."}},
                timeout=30
            )
            
            if chat_response.status_code == 201:
                return {"success": True, "type": "chat"}
            
            if chat_response.status_code == 409:
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
                                json={"text": f"Bună ziua! Aș dori să vă fac o ofertă de {offer_price} RON pentru acest produs. Prețul dvs. este {original_price} RON. Vă rog să luați în considerare oferta mea."},
                                timeout=30
                            )
                            if msg_response.status_code == 201:
                                return {"success": True, "type": "chat"}
            
            return {"error": "Не удалось отправить предложение"}
        
        if response.status_code == 201:
            return {"success": True, "type": "offer"}
        
        if response.status_code == 401:
            return {"error": "Токен устарел. Обновите куки!"}
        
        if response.status_code == 403:
            return {"error": "Доступ запрещен. Проверьте куки!"}
        
        if response.status_code == 409:
            return {"error": "Вы уже отправляли предложение на это объявление"}
        
        return {"error": f"Ошибка {response.status_code}: {response.text[:200]}"}
        
    except requests.exceptions.Timeout:
        return {"error": "Таймаут соединения"}
    except requests.exceptions.ConnectionError:
        return {"error": "Ошибка соединения"}
    except Exception as e:
        return {"error": str(e)}

# ===== КЛАВИАТУРЫ =====
def main_menu():
    d = get_data()
    status_cookies = "✅" if d['cookies'] else "⬜️"
    status_ads = "✅" if d['ads'] else "⬜️"
    
    keyboard = [
        [InlineKeyboardButton(f"🍪 Куки {status_cookies}", callback_data="cookies_menu")],
        [InlineKeyboardButton(f"📦 Объявления {status_ads}", callback_data="ads_menu")],
        [InlineKeyboardButton("📝 Текст сообщения", callback_data="texts_menu")],
        [InlineKeyboardButton("⚙️ НАСТРОЙКИ", callback_data="settings_menu")],
        [InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="stats")],
        [InlineKeyboardButton("💰 ОТПРАВИТЬ ПРЕДЛОЖЕНИЕ", callback_data="send_offer")],
        [InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])

def ads_list_menu():
    ads = load_ads()
    keyboard = []
    for i, ad in enumerate(ads[:30]):
        price = ad.get('price', '')
        title = ad.get('title', '')[:25]
        keyboard.append([InlineKeyboardButton(f"{i+1}. {title} {price}", callback_data=f"ad_{i}")])
    if not ads:
        keyboard.append([InlineKeyboardButton("❌ Нет объявлений", callback_data="main_menu")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def offer_options_menu(ad_title, original_price, offer_price):
    keyboard = [
        [InlineKeyboardButton(f"💰 Предложить {offer_price} RON", callback_data="offer_confirm")],
        [InlineKeyboardButton("✏️ Своя цена", callback_data="offer_custom")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== ОБРАБОТЧИКИ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 OLX Price Offer Bot\n\n"
        "💰 Бот отправляет предложения цены для ВСЕХ категорий!\n\n"
        "1️⃣ Загрузите куки\n"
        "2️⃣ Загрузите CSV с объявлениями\n"
        "3️⃣ Нажмите «Отправить предложение»\n"
        "4️⃣ Бот сам предложит цену на 1 лей меньше!\n\n"
        "⬇️ Используйте кнопки ниже",
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
        msg = (
            f"📊 СТАТИСТИКА\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🍪 Куки: {'✅' if d['cookies'] else '⬜️'} ({len(d['cookies'])} шт.)\n"
            f"📦 Объявления: {'✅' if d['ads'] else '⬜️'} ({len(d['ads'])} шт.)\n"
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
            "📌 Как это работает:\n"
            "1. Бот читает цену из CSV\n"
            "2. Предлагает на 1 лей меньше\n"
            "3. Отправляет предложение в чат продавца",
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

    # ===== ОБЪЯВЛЕНИЯ =====
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
        await query.edit_message_text("📤 Отправьте CSV-файл\nФормат: title,price,ad_url", reply_markup=back_button())
        context.user_data['action'] = 'upload_csv'
        return

    if data == "list_ads":
        d = get_data()
        if not d['ads']:
            await query.edit_message_text("❌ Нет объявлений.", reply_markup=back_button())
            return
        msg = "📋 ОБЪЯВЛЕНИЯ\n\n"
        for i, ad in enumerate(d['ads'][:20]):
            msg += f"{i+1}. {ad.get('title', '')[:40]} — {ad.get('price', '')}\n"
        if len(d['ads']) > 20:
            msg += f"\n... и ещё {len(d['ads']) - 20} объявлений"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_ads":
        save_ads([])
        await query.edit_message_text("✅ Объявления удалены!", reply_markup=main_menu())
        return

    # ===== ТЕКСТЫ =====
    if data == "texts_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить текст", callback_data="add_text")],
            [InlineKeyboardButton("📤 Загрузить файл", callback_data="upload_texts_file")],
            [InlineKeyboardButton("📋 Список текстов", callback_data="list_texts")],
            [InlineKeyboardButton("🗑️ Удалить все", callback_data="clear_texts")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        d = get_data()
        await query.edit_message_text(
            f"📝 ТЕКСТЫ\n\nВсего: {len(d['texts'])} шт.\n\nПеременные:\n{{title}} — название\n{{price}} — цена\n{{offer}} — предложение",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "add_text":
        await query.edit_message_text(
            "✏️ Отправьте текст\n\nПеременные:\n{title} — название\n{price} — цена\n{offer} — ваше предложение",
            reply_markup=back_button()
        )
        context.user_data['action'] = 'add_text'
        return

    if data == "upload_texts_file":
        await query.edit_message_text("📤 Отправьте файл texts.txt", reply_markup=back_button())
        context.user_data['action'] = 'upload_texts_file'
        return

    if data == "list_texts":
        d = get_data()
        if not d['texts']:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        msg = "📋 ТЕКСТЫ\n\n"
        for i, t in enumerate(d['texts'][:20]):
            msg += f"{i+1}. {t[:100]}{'...' if len(t) > 100 else ''}\n\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=back_button())
        return

    if data == "clear_texts":
        save_texts([])
        await query.edit_message_text("✅ Тексты удалены!", reply_markup=main_menu())
        return

    # ===== НАСТРОЙКИ =====
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
            [InlineKeyboardButton("3 сек", callback_data="delay_3")],
            [InlineKeyboardButton("5 сек", callback_data="delay_5")],
            [InlineKeyboardButton("10 сек", callback_data="delay_10")],
            [InlineKeyboardButton("15 сек", callback_data="delay_15")],
            [InlineKeyboardButton("20 сек", callback_data="delay_20")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
        ]
        await query.edit_message_text(f"⏱ ВЫБЕРИТЕ ЗАДЕРЖКУ\n\nТекущая: {get_delay()} сек", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("delay_"):
        seconds = int(data.split("_")[1])
        set_delay(seconds)
        await query.edit_message_text(f"✅ Задержка: {seconds} сек", parse_mode='HTML', reply_markup=main_menu())
        return

    if data == "clear_all":
        save_cookies([])
        save_ads([])
        save_texts([])
        await query.edit_message_text("🔄 ВСЕ ДАННЫЕ ОЧИЩЕНЫ!", parse_mode='HTML', reply_markup=main_menu())
        return

    # ===== ОТПРАВКА ПРЕДЛОЖЕНИЯ =====
    if data == "send_offer":
        ads = load_ads()
        if not ads:
            await query.edit_message_text("❌ Нет объявлений! Загрузите CSV.", reply_markup=back_button())
            return
        
        cookies = load_cookies()
        if not cookies:
            await query.edit_message_text("❌ Нет кук! Загрузите куки.", reply_markup=back_button())
            return
        
        await query.edit_message_text("💰 ВЫБЕРИТЕ ОБЪЯВЛЕНИЕ", parse_mode='HTML', reply_markup=ads_list_menu())
        return

    # ===== ВЫБОР ОБЪЯВЛЕНИЯ =====
    if data.startswith("ad_"):
        index = int(data.split("_")[1])
        ads = load_ads()
        if index >= len(ads):
            await query.edit_message_text("❌ Объявление не найдено", reply_markup=back_button())
            return
        
        ad = ads[index]
        context.user_data['selected_ad'] = ad
        context.user_data['selected_ad_index'] = index
        
        original_price = extract_price(ad.get('price', ''))
        if not original_price:
            await query.edit_message_text(
                f"❌ Не удалось извлечь цену из: {ad.get('price', '')}\n\n"
                f"Проверьте формат в CSV (например: 1000 lei)",
                reply_markup=back_button()
            )
            return
        
        offer_price = original_price - 1
        
        await query.edit_message_text(
            f"💰 ПРЕДЛОЖЕНИЕ ЦЕНЫ\n\n"
            f"📌 {ad.get('title', '')}\n"
            f"💰 Цена продавца: {original_price} RON\n"
            f"💡 Ваше предложение: {offer_price} RON (-1 лей)\n\n"
            f"Выберите действие:",
            parse_mode='HTML',
            reply_markup=offer_options_menu(ad.get('title', ''), original_price, offer_price)
        )
        return

    # ===== ПОДТВЕРЖДЕНИЕ ПРЕДЛОЖЕНИЯ =====
    if data == "offer_confirm":
        ad = context.user_data.get('selected_ad')
        if not ad:
            await query.edit_message_text("❌ Ошибка: объявление не выбрано", reply_markup=back_button())
            return
        
        original_price = extract_price(ad.get('price', ''))
        offer_price = original_price - 1 if original_price else 0
        
        await query.edit_message_text(
            f"🚀 ОТПРАВКА ПРЕДЛОЖЕНИЯ...\n\n"
            f"📌 {ad.get('title', '')[:40]}\n"
            f"💰 Цена: {original_price} RON\n"
            f"💡 Предложение: {offer_price} RON\n\n"
            f"⏳ Пожалуйста, подождите...",
            parse_mode='HTML'
        )
        
        result = send_offer_via_api(ad['url'], offer_price, original_price)
        
        if result.get('success'):
            offer_type = "официальное предложение" if result.get('type') == 'offer' else "сообщение в чат"
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=f"✅ ПРЕДЛОЖЕНИЕ ОТПРАВЛЕНО!\n\n"
                f"📌 {ad.get('title', '')[:40]}\n"
                f"💰 Цена: {original_price} RON\n"
                f"💡 Предложено: {offer_price} RON\n"
                f"📨 Тип: {offer_type}",
                parse_mode='HTML',
                reply_markup=main_menu()
            )
        else:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=f"❌ ОШИБКА\n\n{result.get('error', 'Неизвестная ошибка')}",
                parse_mode='HTML',
                reply_markup=main_menu()
            )
        return

    # ===== СВОЯ ЦЕНА =====
    if data == "offer_custom":
        await query.edit_message_text(
            "✏️ Введите свою цену в чат\n\n"
            "Просто напишите число (например: 150)",
            reply_markup=back_button()
        )
        context.user_data['action'] = 'custom_offer'
        return

# ===== ОБРАБОТЧИК ФАЙЛОВ =====
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
            await update.message.reply_text(f"✅ КУКИ ЗАГРУЖЕНЫ!\n\nКоличество: {len(cookies)} шт.", parse_mode='HTML', reply_markup=main_menu())
            return
    except:
        pass

    if file_name.endswith('.csv'):
        parsed = parse_csv_text(text)
        if parsed:
            save_ads(parsed)
            await update.message.reply_text(f"✅ CSV ЗАГРУЖЕН!\n\nОбъявлений: {len(parsed)}", parse_mode='HTML', reply_markup=main_menu())
        else:
            await update.message.reply_text("❌ Не удалось распарсить CSV.\nФормат: title,price,ad_url", reply_markup=back_button())
        return

    if "text" in file_name or file_name == "texts.txt":
        texts = [line.strip() for line in text.split('\n') if line.strip()]
        if texts:
            save_texts(texts)
            await update.message.reply_text(f"✅ ТЕКСТЫ ЗАГРУЖЕНЫ!\n\nКоличество: {len(texts)} шт.", parse_mode='HTML', reply_markup=main_menu())
        return

    await update.message.reply_text(f"⚠️ Неизвестный файл: {file_name}", reply_markup=back_button())

# ===== ОБРАБОТЧИК ТЕКСТА =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    text = update.message.text.strip()

    if not action:
        await update.message.reply_text("Используйте меню.", reply_markup=main_menu())
        return

    if action == 'upload_cookies':
        try:
            cookies = json.loads(text)
            if isinstance(cookies, list) and len(cookies) > 0:
                save_cookies(cookies)
                await update.message.reply_text(f"✅ КУКИ ЗАГРУЖЕНЫ!\n\nКоличество: {len(cookies)} шт.", parse_mode='HTML', reply_markup=main_menu())
            else:
                await update.message.reply_text("❌ Неверный формат. Ожидается JSON-массив.", reply_markup=back_button())
        except:
            await update.message.reply_text("❌ Неверный JSON.", reply_markup=back_button())
        user_data['action'] = None
        return

    if action == 'add_text':
        texts = load_texts()
        texts.append(text)
        save_texts(texts)
        await update.message.reply_text(f"✅ Текст добавлен!\nВсего: {len(texts)}", reply_markup=main_menu())
        user_data['action'] = None
        return

    if action == 'upload_texts_file':
        texts = [t.strip() for t in text.split('\n') if t.strip()]
        if texts:
            save_texts(texts)
            await update.message.reply_text(f"✅ Тексты загружены! {len(texts)} шт.", reply_markup=main_menu())
        user_data['action'] = None
        return

    if action == 'upload_csv':
        await update.message.reply_text("❌ Отправьте CSV-файл.", reply_markup=back_button())
        user_data['action'] = None
        return

    if action == 'custom_offer':
        try:
            custom_price = int(text)
            ad = context.user_data.get('selected_ad')
            if not ad:
                await update.message.reply_text("❌ Ошибка: объявление не выбрано", reply_markup=back_button())
                user_data['action'] = None
                return
            
            original_price = extract_price(ad.get('price', ''))
            
            await update.message.reply_text(
                f"🚀 ОТПРАВКА ПРЕДЛОЖЕНИЯ...\n\n"
                f"📌 {ad.get('title', '')[:40]}\n"
                f"💰 Ваше предложение: {custom_price} RON\n"
                f"⏳ Пожалуйста, подождите...",
                parse_mode='HTML'
            )
            
            result = send_offer_via_api(ad['url'], custom_price, original_price if original_price else 0)
            
            if result.get('success'):
                offer_type = "официальное предложение" if result.get('type') == 'offer' else "сообщение в чат"
                await update.message.reply_text(
                    f"✅ ПРЕДЛОЖЕНИЕ ОТПРАВЛЕНО!\n\n"
                    f"📌 {ad.get('title', '')[:40]}\n"
                    f"💰 Предложено: {custom_price} RON\n"
                    f"📨 Тип: {offer_type}",
                    parse_mode='HTML',
                    reply_markup=main_menu()
                )
            else:
                await update.message.reply_text(
                    f"❌ ОШИБКА\n\n{result.get('error', 'Неизвестная ошибка')}",
                    parse_mode='HTML',
                    reply_markup=main_menu()
                )
        except ValueError:
            await update.message.reply_text("❌ Введите число (например: 150)", reply_markup=back_button())
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
