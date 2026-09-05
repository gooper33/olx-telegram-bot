import os
import csv
import json
import asyncio
import re
import random
from datetime import datetime
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
        "tokens": [],
        "proxies": [],
        "texts": [],
        "ads": [],
        "delay": 5  # задержка по умолчанию 5 секунд
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# ===== КЛАВИАТУРЫ =====
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🔑 Управление токенами", callback_data="tokens_menu")],
        [InlineKeyboardButton("🌐 Управление прокси", callback_data="proxies_menu")],
        [InlineKeyboardButton("📝 Управление текстами", callback_data="texts_menu")],
        [InlineKeyboardButton("⏱ Настройка задержки", callback_data="delay_menu")],
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
    
    if query.data == "main_menu":
        await query.edit_message_text("👋 <b>Главное меню</b>", parse_mode='HTML', reply_markup=main_menu())
    
    elif query.data == "stats":
        await query.edit_message_text(
            f"📊 <b>Статистика</b>\n\n"
            f"🔑 Токенов: <b>{len(data['tokens'])}</b>\n"
            f"🌐 Прокси: <b>{len(data['proxies'])}</b>\n"
            f"📝 Текстов: <b>{len(data['texts'])}</b>\n"
            f"📦 Объявлений: <b>{len(data['ads'])}</b>\n"
            f"⏱ Задержка: <b>{data.get('delay', 5)} сек</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    # ===== ЗАДЕРЖКА =====
    elif query.data == "delay_menu":
        keyboard = [
            [InlineKeyboardButton("1 сек", callback_data="delay_1")],
            [InlineKeyboardButton("3 сек", callback_data="delay_3")],
            [InlineKeyboardButton("5 сек", callback_data="delay_5")],
            [InlineKeyboardButton("10 сек", callback_data="delay_10")],
            [InlineKeyboardButton("15 сек", callback_data="delay_15")],
            [InlineKeyboardButton("30 сек", callback_data="delay_30")],
            [InlineKeyboardButton("60 сек", callback_data="delay_60")],
            [InlineKeyboardButton("✏️ Своё значение", callback_data="delay_custom")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        current_delay = data.get('delay', 5)
        await query.edit_message_text(
            f"⏱ <b>Настройка задержки</b>\n\n"
            f"Текущая задержка: <b>{current_delay} сек</b>\n\n"
            f"Выберите задержку между отправками:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("delay_"):
        if query.data == "delay_custom":
            context.user_data['action'] = 'set_delay'
            await query.edit_message_text(
                "✏️ <b>Введите задержку в секундах</b>\n\n"
                "Например: <code>10</code> (будет 10 секунд между отправками)",
                parse_mode='HTML',
                reply_markup=back_button()
            )
        else:
            seconds = int(query.data.split("_")[1])
            data['delay'] = seconds
            save_data(data)
            await query.edit_message_text(
                f"✅ Задержка установлена: <b>{seconds} сек</b>",
                parse_mode='HTML',
                reply_markup=main_menu()
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
            f"🔑 <b>Управление токенами</b>\n\nВсего: {len(data['tokens'])}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_token":
        context.user_data['action'] = 'add_token'
        await query.edit_message_text(
            "🔑 Отправьте токен от @BotFather.\n\nМожно несколько, каждый с новой строки.",
            reply_markup=back_button()
        )
    
    elif query.data == "list_tokens":
        if not data['tokens']:
            await query.edit_message_text("❌ Нет токенов.", reply_markup=back_button())
            return
        text = "\n".join([f"{i+1}. <code>{t[:15]}...{t[-5:]}</code>" for i, t in enumerate(data['tokens'])])
        await query.edit_message_text(f"📋 <b>Токены</b>\n\n{text}", parse_mode='HTML', reply_markup=back_button())
    
    elif query.data == "delete_token":
        if not data['tokens']:
            await query.edit_message_text("❌ Нет токенов.", reply_markup=back_button())
            return
        keyboard = [[InlineKeyboardButton(f"🗑️ {t[:15]}...", callback_data=f"del_token_{i}")] for i, t in enumerate(data['tokens'])]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="tokens_menu")])
        await query.edit_message_text("🗑️ Выберите токен для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data.startswith("del_token_"):
        idx = int(query.data.split("_")[2])
        data['tokens'].pop(idx)
        save_data(data)
        await query.edit_message_text(f"✅ Удалено. Осталось: {len(data['tokens'])}", reply_markup=back_button())
    
    # ===== ПРОКСИ =====
    elif query.data == "proxies_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить прокси", callback_data="add_proxy")],
            [InlineKeyboardButton("📋 Список прокси", callback_data="list_proxies")],
            [InlineKeyboardButton("🗑️ Удалить прокси", callback_data="delete_proxy")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🌐 <b>Управление прокси</b>\n\nВсего: {len(data['proxies'])}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_proxy":
        context.user_data['action'] = 'add_proxy'
        await query.edit_message_text(
            "🌐 Отправьте прокси в формате:\n<code>http://user:pass@ip:port</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "list_proxies":
        if not data['proxies']:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        text = "\n".join([f"{i+1}. <code>{p}</code>" for i, p in enumerate(data['proxies'])])
        await query.edit_message_text(f"📋 <b>Прокси</b>\n\n{text}", parse_mode='HTML', reply_markup=back_button())
    
    elif query.data == "delete_proxy":
        if not data['proxies']:
            await query.edit_message_text("❌ Нет прокси.", reply_markup=back_button())
            return
        keyboard = [[InlineKeyboardButton(f"🗑️ {p[:20]}...", callback_data=f"del_proxy_{i}")] for i, p in enumerate(data['proxies'])]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="proxies_menu")])
        await query.edit_message_text("🗑️ Выберите прокси для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data.startswith("del_proxy_"):
        idx = int(query.data.split("_")[2])
        data['proxies'].pop(idx)
        save_data(data)
        await query.edit_message_text(f"✅ Удалено. Осталось: {len(data['proxies'])}", reply_markup=back_button())
    
    # ===== ТЕКСТЫ =====
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
    
    elif query.data == "add_text":
        context.user_data['action'] = 'add_text'
        await query.edit_message_text(
            "📝 Отправьте текст для рассылки.\n\n"
            "Переменные:\n"
            "<code>{title}</code> - название\n"
            "<code>{price}</code> - цена\n"
            "<code>{city}</code> - город\n"
            "<code>{url}</code> - ссылка\n\n"
            "Можно несколько, разделяя <code>---</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "list_texts":
        if not data['texts']:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        text = "\n\n---\n\n".join([f"{i+1}. {t[:100]}..." if len(t) > 100 else f"{i+1}. {t}" for i, t in enumerate(data['texts'])])
        await query.edit_message_text(f"📋 <b>Тексты</b>\n\n{text}", parse_mode='HTML', reply_markup=back_button())
    
    elif query.data == "delete_text":
        if not data['texts']:
            await query.edit_message_text("❌ Нет текстов.", reply_markup=back_button())
            return
        keyboard = [[InlineKeyboardButton(f"🗑️ {t[:20]}...", callback_data=f"del_text_{i}")] for i, t in enumerate(data['texts'])]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="texts_menu")])
        await query.edit_message_text("🗑️ Выберите текст для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data.startswith("del_text_"):
        idx = int(query.data.split("_")[2])
        data['texts'].pop(idx)
        save_data(data)
        await query.edit_message_text(f"✅ Удалено. Осталось: {len(data['texts'])}", reply_markup=back_button())
    
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
        await query.edit_message_text("🚀 <b>Подготовка к рассылке...</b>", parse_mode='HTML')
        
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
        
        await query.edit_message_text(
            f"🚀 <b>Начинаю рассылку...</b>\n\n"
            f"📦 Объявлений: {len(data['ads'])}\n"
            f"🔑 Токенов: {len(data['tokens'])}\n"
            f"📝 Текстов: {len(data['texts'])}\n"
            f"🌐 Прокси: {len(data['proxies'])}\n"
            f"⏱ Задержка: {data.get('delay', 5)} сек\n\n"
            f"⏳ Пожалуйста, подождите...",
            parse_mode='HTML'
        )
        
        result = await send_all_ads(context, query.from_user.id)
        
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=result,
            parse_mode='HTML',
            reply_markup=main_menu()
        )
    
    elif query.data == "clear_all":
        data['tokens'] = []
        data['proxies'] = []
        data['texts'] = []
        data['ads'] = []
        data['delay'] = 5
        save_data(data)
        await query.edit_message_text("🔄 <b>Все данные очищены</b>", parse_mode='HTML', reply_markup=main_menu())

# ===== ФУНКЦИЯ РАССЫЛКИ =====
async def send_all_ads(context, chat_id) -> str:
    ads = data['ads']
    texts = data['texts']
    tokens = data['tokens']
    proxies = data['proxies']
    delay = data.get('delay', 5)
    
    total = len(ads)
    sent = 0
    errors = []
    banned_tokens = []
    
    for i, ad in enumerate(ads, 1):
        try:
            text_template = random.choice(texts)
            
            message_text = text_template.format(
                title=ad.get('title', 'Без названия'),
                price=ad.get('price', 'Цена не указана'),
                city=ad.get('city', 'Не указано'),
                seller=ad.get('seller', 'Продавец'),
                description=ad.get('description', '')[:300],
                url=ad.get('ad_url', '#')
            )
            
            token = tokens[i % len(tokens)]
            
            from telegram import Bot
            from telegram.request import HTTPXRequest
            
            if proxies:
                proxy = proxies[i % len(proxies)]
                request = HTTPXRequest(proxy=proxy)
                bot = Bot(token=token, request=request)
            else:
                bot = Bot(token=token)
            
            if ad.get('image_url') and ad['image_url'].startswith('http'):
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=ad['image_url'],
                    caption=message_text,
                    parse_mode='HTML'
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode='HTML'
                )
            
            sent += 1
            
            # ЗАДЕРЖКА ПОСЛЕ КАЖДОГО ОБЪЯВЛЕНИЯ
            if i < total:
                await asyncio.sleep(delay)
            
        except Exception as e:
            error_msg = str(e)
            if "Unauthorized" in error_msg or "Invalid token" in error_msg or "Forbidden" in error_msg:
                banned_tokens.append(token)
                errors.append(f"❌ Токен {token[:10]}... забанен: {error_msg[:100]}")
            else:
                errors.append(f"⚠️ Ошибка в объявлении {i}: {error_msg[:100]}")
            
            if len(banned_tokens) == len(tokens):
                break
    
    report = f"✅ <b>Рассылка завершена!</b>\n\n"
    report += f"📦 <b>Статистика:</b>\n"
    report += f"Всего объявлений: <b>{total}</b>\n"
    report += f"Отправлено успешно: <b>{sent}</b>\n"
    report += f"Ошибок: <b>{len(errors)}</b>\n"
    report += f"⏱ Задержка: <b>{delay} сек</b>\n\n"
    
    if banned_tokens:
        report += f"🚫 <b>Забаненные токены:</b>\n"
        for t in banned_tokens:
            report += f"- <code>{t[:15]}...{t[-5:]}</code>\n"
        report += f"\n💡 Удалите их через меню.\n\n"
    
    if errors:
        report += f"📋 <b>Последние ошибки:</b>\n"
        for err in errors[:5]:
            report += f"{err}\n"
        if len(errors) > 5:
            report += f"... и ещё {len(errors) - 5} ошибок\n"
    
    return report

# ===== ОБРАБОТЧИК СООБЩЕНИЙ =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    
    if not action:
        await update.message.reply_text("Используйте /start для открытия меню.")
        return
    
    text = update.message.text
    
    if action == 'add_token':
        new_tokens = [t.strip() for t in text.split('\n') if t.strip()]
        data['tokens'].extend(new_tokens)
        save_data(data)
        await update.message.reply_text(
            f"✅ Добавлено токенов: <b>{len(new_tokens)}</b>\n\nВсего: <b>{len(data['tokens'])}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
    
    elif action == 'add_proxy':
        new_proxies = [p.strip() for p in text.split('\n') if p.strip()]
        data['proxies'].extend(new_proxies)
        save_data(data)
        await update.message.reply_text(
            f"✅ Добавлено прокси: <b>{len(new_proxies)}</b>\n\nВсего: <b>{len(data['proxies'])}</b>",
            parse_mode='HTML',
            reply_markup=main_menu()
        )
        user_data['action'] = None
    
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
    
    elif action == 'set_delay':
        try:
            seconds = int(text.strip())
            if seconds < 1:
                await update.message.reply_text("❌ Задержка должна быть больше 0 секунд.")
                return
            data['delay'] = seconds
            save_data(data)
            await update.message.reply_text(
                f"✅ Задержка установлена: <b>{seconds} сек</b>",
                parse_mode='HTML',
                reply_markup=main_menu()
            )
        except ValueError:
            await update.message.reply_text("❌ Введите число (например, 10)")
        user_data['action'] = None

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

def parse_csv_text(content: str) -> list:
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
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден в переменных окружения!")
        print("Добавьте переменную BOT_TOKEN в Render (Environment → Environment Variables)")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_csv_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()