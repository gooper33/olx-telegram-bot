import os
import csv
import json
import asyncio
import re
from io import BytesIO
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import random

# ===== ФАЙЛЫ ДЛЯ ХРАНЕНИЯ ДАННЫХ =====
DATA_FILE = "data.json"

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ =====
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "tokens": [],  # ["токен1", "токен2"]
        "proxies": [],  # ["http://user:pass@ip:port", ...]
        "texts": [],  # ["текст1", "текст2"]
        "ads": []  # список объявлений из CSV
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()
pending_csv = None  # временное хранение CSV перед загрузкой

# ===== КЛАВИАТУРЫ =====
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🔑 Управление токенами", callback_data="tokens_menu")],
        [InlineKeyboardButton("🌐 Управление прокси", callback_data="proxies_menu")],
        [InlineKeyboardButton("📝 Управление текстами", callback_data="texts_menu")],
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
        "📌 Управляйте рассылкой через меню.\n"
        "Добавьте токены, прокси, тексты и загрузите CSV с объявлениями.",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "main_menu":
        await query.edit_message_text(
            "👋 <b>Главное меню</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
    
    elif query.data == "stats":
        count_tokens = len(data['tokens'])
        count_proxies = len(data['proxies'])
        count_texts = len(data['texts'])
        count_ads = len(data['ads'])
        
        await query.edit_message_text(
            f"📊 <b>Статистика</b>\n\n"
            f"🔑 Токенов: <b>{count_tokens}</b>\n"
            f"🌐 Прокси: <b>{count_proxies}</b>\n"
            f"📝 Текстов: <b>{count_texts}</b>\n"
            f"📦 Объявлений: <b>{count_ads}</b>\n\n"
            f"{'✅ Готово к рассылке' if count_tokens > 0 and count_ads > 0 else '❌ Добавьте токены и загрузите CSV'}",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    # ===== ТОКЕНЫ =====
    elif query.data == "tokens_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить токен", callback_data="add_token")],
            [InlineKeyboardButton("📋 Список токенов", callback_data="list_tokens")],
            [InlineKeyboardButton("🗑️ Удалить токен", callback_data="delete_token")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🔑 <b>Управление токенами</b>\n\n"
            f"Всего токенов: <b>{len(data['tokens'])}</b>\n\n"
            f"Токены нужны для отправки сообщений. Каждый токен = один аккаунт.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_token":
        context.user_data['action'] = 'add_token'
        await query.edit_message_text(
            "🔑 <b>Добавление токена</b>\n\n"
            "Отправьте мне токен от @BotFather.\n\n"
            "Пример: <code>1234567890:ABCdefGHIjklMNOpqrsTUVwxyz</code>\n\n"
            "Или отправьте несколько токенов, каждый с новой строки.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "list_tokens":
        if not data['tokens']:
            await query.edit_message_text(
                "❌ Токены не добавлены.",
                reply_markup=back_button()
            )
            return
        
        tokens_list = "\n".join([f"{i+1}. <code>{t[:15]}...{t[-5:]}</code>" for i, t in enumerate(data['tokens'])])
        await query.edit_message_text(
            f"📋 <b>Список токенов</b>\n\n{tokens_list}\n\n"
            f"Всего: <b>{len(data['tokens'])}</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "delete_token":
        if not data['tokens']:
            await query.edit_message_text(
                "❌ Нет токенов для удаления.",
                reply_markup=back_button()
            )
            return
        
        keyboard = []
        for i, token in enumerate(data['tokens']):
            short = f"{token[:10]}...{token[-5:]}" if len(token) > 15 else token
            keyboard.append([InlineKeyboardButton(f"🗑️ {short}", callback_data=f"del_token_{i}")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="tokens_menu")])
        
        await query.edit_message_text(
            "🗑️ <b>Выберите токен для удаления</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("del_token_"):
        index = int(query.data.split("_")[2])
        deleted = data['tokens'].pop(index)
        save_data(data)
        await query.edit_message_text(
            f"✅ Токен удалён.\n\nОсталось: <b>{len(data['tokens'])}</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    # ===== ПРОКСИ =====
    elif query.data == "proxies_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить прокси", callback_data="add_proxy")],
            [InlineKeyboardButton("📋 Список прокси", callback_data="list_proxies")],
            [InlineKeyboardButton("🗑️ Удалить прокси", callback_data="delete_proxy")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🌐 <b>Управление прокси</b>\n\n"
            f"Всего прокси: <b>{len(data['proxies'])}</b>\n\n"
            f"Формат: <code>http://user:pass@ip:port</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_proxy":
        context.user_data['action'] = 'add_proxy'
        await query.edit_message_text(
            "🌐 <b>Добавление прокси</b>\n\n"
            "Отправьте прокси в формате:\n"
            "<code>http://user:pass@ip:port</code>\n\n"
            "Или несколько прокси, каждый с новой строки.",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "list_proxies":
        if not data['proxies']:
            await query.edit_message_text(
                "❌ Прокси не добавлены.",
                reply_markup=back_button()
            )
            return
        
        proxies_list = "\n".join([f"{i+1}. <code>{p}</code>" for i, p in enumerate(data['proxies'])])
        await query.edit_message_text(
            f"📋 <b>Список прокси</b>\n\n{proxies_list}\n\n"
            f"Всего: <b>{len(data['proxies'])}</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "delete_proxy":
        if not data['proxies']:
            await query.edit_message_text(
                "❌ Нет прокси для удаления.",
                reply_markup=back_button()
            )
            return
        
        keyboard = []
        for i, proxy in enumerate(data['proxies']):
            short = f"{proxy[:20]}..." if len(proxy) > 25 else proxy
            keyboard.append([InlineKeyboardButton(f"🗑️ {short}", callback_data=f"del_proxy_{i}")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="proxies_menu")])
        
        await query.edit_message_text(
            "🗑️ <b>Выберите прокси для удаления</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("del_proxy_"):
        index = int(query.data.split("_")[2])
        deleted = data['proxies'].pop(index)
        save_data(data)
        await query.edit_message_text(
            f"✅ Прокси удалён.\n\nОсталось: <b>{len(data['proxies'])}</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    # ===== ТЕКСТЫ =====
    elif query.data == "texts_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить текст", callback_data="add_text")],
            [InlineKeyboardButton("📋 Список текстов", callback_data="list_texts")],
            [InlineKeyboardButton("🗑️ Удалить текст", callback_data="delete_text")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"📝 <b>Управление текстами</b>\n\n"
            f"Всего текстов: <b>{len(data['texts'])}</b>\n\n"
            f"Тексты будут подставляться случайным образом к каждому объявлению.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_text":
        context.user_data['action'] = 'add_text'
        await query.edit_message_text(
            "📝 <b>Добавление текста</b>\n\n"
            "Отправьте текст для рассылки.\n"
            "Можно использовать переменные:\n"
            "<code>{title}</code> - название\n"
            "<code>{price}</code> - цена\n"
            "<code>{city}</code> - город\n"
            "<code>{seller}</code> - продавец\n"
            "<code>{description}</code> - описание\n"
            "<code>{url}</code> - ссылка\n\n"
            "Или отправьте несколько текстов, каждый с новой строки (разделитель ---)",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "list_texts":
        if not data['texts']:
            await query.edit_message_text(
                "❌ Тексты не добавлены.",
                reply_markup=back_button()
            )
            return
        
        texts_list = "\n\n---\n\n".join([f"{i+1}. {t[:100]}..." if len(t) > 100 else f"{i+1}. {t}" for i, t in enumerate(data['texts'])])
        await query.edit_message_text(
            f"📋 <b>Список текстов</b>\n\n{texts_list}\n\n"
            f"Всего: <b>{len(data['texts'])}</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "delete_text":
        if not data['texts']:
            await query.edit_message_text(
                "❌ Нет текстов для удаления.",
                reply_markup=back_button()
            )
            return
        
        keyboard = []
        for i, text in enumerate(data['texts']):
            short = f"{text[:20]}..." if len(text) > 25 else text
            keyboard.append([InlineKeyboardButton(f"🗑️ {short}", callback_data=f"del_text_{i}")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="texts_menu")])
        
        await query.edit_message_text(
            "🗑️ <b>Выберите текст для удаления</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("del_text_"):
        index = int(query.data.split("_")[2])
        deleted = data['texts'].pop(index)
        save_data(data)
        await query.edit_message_text(
            f"✅ Текст удалён.\n\nОсталось: <b>{len(data['texts'])}</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    # ===== CSV =====
    elif query.data == "upload_csv":
        context.user_data['action'] = 'upload_csv'
        await query.edit_message_text(
            "📤 <b>Загрузка CSV</b>\n\n"
            "Отправьте мне CSV-файл с объявлениями.\n\n"
            "Формат:\n"
            "<code>country,title,price,publication,seller,registration,phone,ad_url,image_url,city,category,description</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    # ===== РАССЫЛКА =====
    elif query.data == "start_send":
        await query.edit_message_text(
            "🚀 <b>Подготовка к рассылке...</b>",
            parse_mode='HTML'
        )
        
        # Проверка данных
        errors = []
        if not data['tokens']:
            errors.append("❌ Нет токенов")
        if not data['texts']:
            errors.append("❌ Нет текстов")
        if not data['ads']:
            errors.append("❌ Нет объявлений (загрузите CSV)")
        
        if errors:
            await query.edit_message_text(
                "⚠️ <b>Нельзя начать рассылку</b>\n\n" + "\n".join(errors),
                parse_mode='HTML',
                reply_markup=back_button()
            )
            return
        
        # Запускаем рассылку
        await query.edit_message_text(
            f"🚀 <b>Начинаю рассылку...</b>\n\n"
            f"📦 Объявлений: {len(data['ads'])}\n"
            f"🔑 Токенов: {len(data['tokens'])}\n"
            f"📝 Текстов: {len(data['texts'])}\n"
            f"🌐 Прокси: {len(data['proxies'])}\n\n"
            f"⏳ Пожалуйста, подождите...",
            parse_mode='HTML'
        )
        
        # Здесь запускается рассылка
        sent = await send_all_ads(context, query.from_user.id)
        
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"✅ <b>Рассылка завершена!</b>\n\nОтправлено: <b>{sent}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
    
    elif query.data == "clear_all":
        data['tokens'] = []
        data['proxies'] = []
        data['texts'] = []
        data['ads'] = []
        save_data(data)
        await query.edit_message_text(
            "🔄 <b>Все данные очищены</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )

# ===== ФУНКЦИЯ РАССЫЛКИ =====
async def send_all_ads(context, chat_id):
    """Рассылка объявлений с случайными текстами и ротацией токенов/прокси"""
    sent = 0
    ads = data['ads']
    texts = data['texts']
    tokens = data['tokens']
    proxies = data['proxies']
    
    for i, ad in enumerate(ads, 1):
        # Выбираем случайный текст
        text_template = random.choice(texts)
        
        # Подставляем переменные
        message_text = text_template.format(
            title=ad.get('title', 'Без названия'),
            price=ad.get('price', 'Цена не указана'),
            city=ad.get('city', 'Не указано'),
            seller=ad.get('seller', 'Продавец'),
            description=ad.get('description', '')[:300],
            url=ad.get('ad_url', '#')
        )
        
        # Выбираем токен и прокси (если есть)
        token = random.choice(tokens)
        proxy = random.choice(proxies) if proxies else None
        
        # Формируем сообщение с фото
        try:
            if ad.get('image_url') and ad['image_url'].startswith('http'):
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=ad['image_url'],
                    caption=message_text,
                    parse_mode='HTML'
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode='HTML'
                )
            sent += 1
            await asyncio.sleep(1)  # задержка
        except Exception as e:
            print(f"Ошибка: {e}")
            continue
    
    return sent

# ===== ОБРАБОТЧИК СООБЩЕНИЙ =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    
    if not action:
        await update.message.reply_text("Используйте /start для открытия меню.")
        return
    
    text = update.message.text
    
    if action == 'add_token':
        # Разбиваем на несколько токенов
        new_tokens = [t.strip() for t in text.split('\n') if t.strip()]
        data['tokens'].extend(new_tokens)
        save_data(data)
        await update.message.reply_text(
            f"✅ Добавлено токенов: <b>{len(new_tokens)}</b>\n\n"
            f"Всего токенов: <b>{len(data['tokens'])}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
    
    elif action == 'add_proxy':
        new_proxies = [p.strip() for p in text.split('\n') if p.strip()]
        data['proxies'].extend(new_proxies)
        save_data(data)
        await update.message.reply_text(
            f"✅ Добавлено прокси: <b>{len(new_proxies)}</b>\n\n"
            f"Всего прокси: <b>{len(data['proxies'])}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
    
    elif action == 'add_text':
        # Разбиваем через разделитель ---
        if '---' in text:
            new_texts = [t.strip() for t in text.split('---') if t.strip()]
        else:
            new_texts = [text.strip()]
        
        data['texts'].extend(new_texts)
        save_data(data)
        await update.message.reply_text(
            f"✅ Добавлено текстов: <b>{len(new_texts)}</b>\n\n"
            f"Всего текстов: <b>{len(data['texts'])}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
    
    elif action == 'upload_csv':
        # Обработка CSV (если прислали текстом)
        try:
            ads = parse_csv_text(text)
            if ads:
                data['ads'] = ads
                save_data(data)
                await update.message.reply_text(
                    f"✅ Загружено объявлений: <b>{len(ads)}</b>\n\n"
                    f"Первое: {ads[0]['title']}\n"
                    f"Цена: {ads[0]['price']}",
                    parse_mode='HTML',
                    reply_markup=main_menu()
                )
            else:
                await update.message.reply_text(
                    "❌ Не удалось распарсить CSV. Проверьте формат.",
                    reply_markup=back_button()
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        user_data['action'] = None

async def handle_csv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик загруженного CSV-файла"""
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
                f"✅ <b>CSV загружен!</b>\n\n"
                f"Объявлений: <b>{len(ads)}</b>\n\n"
                f"Первое: {ads[0]['title']}\n"
                f"💰 {ads[0]['price']}\n"
                f"📍 {ads[0]['city']}",
                parse_mode='HTML',
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text("❌ Не удалось распарсить CSV.", reply_markup=back_button())
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

def parse_csv_text(content: str) -> list:
    """Парсит CSV-текст в список объявлений"""
    lines = content.strip().split('\n')
    if len(lines) < 2:
        return []
    
    header = lines[0].strip().split(',')
    try:
        title_idx = header.index('title')
        price_idx = header.index('price')
        ad_url_idx = header.index('ad_url')
        image_url_idx = header.index('image_url')
        city_idx = header.index('city')
        description_idx = header.index('description')
        seller_idx = header.index('seller')
    except ValueError:
        title_idx, price_idx, ad_url_idx, image_url_idx, city_idx, description_idx, seller_idx = 1, 2, 7, 8, 9, 11, 5
    
    ads = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) < 12:
            continue
        ads.append({
            'title': parts[title_idx] if title_idx < len(parts) else "Без названия",
            'price': parts[price_idx] if price_idx < len(parts) else "Цена не указана",
            'ad_url': parts[ad_url_idx] if ad_url_idx < len(parts) else "#",
            'image_url': parts[image_url_idx] if image_url_idx < len(parts) else "",
            'city': parts[city_idx] if city_idx < len(parts) else "Не указано",
            'description': parts[description_idx] if description_idx < len(parts) else "",
            'seller': parts[seller_idx] if seller_idx < len(parts) else "Продавец"
        })
    return ads

# ===== ЗАПУСК =====
def main():
    app = Application.builder().token("ВАШ_ТОКЕН_ОТ_BOTFATHER").build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_csv_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()