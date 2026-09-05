import os
import csv
import json
import asyncio
import random
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===== ФАЙЛ ДЛЯ ХРАНЕНИЯ ДАННЫХ =====
DATA_FILE = "data.json"
COUNTRY_CODE = "ro"

# ===== ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ =====
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "accounts": [],  # [{"name": "Аккаунт 1", "access_token": "...", "refresh_token": "...", "expires_at": "..."}]
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
        [InlineKeyboardButton("📝 Управление текстами", callback_data="texts_menu")],
        [InlineKeyboardButton("⏱ Задержка", callback_data="delay_menu")],
        [InlineKeyboardButton("📤 Загрузить CSV", callback_data="upload_csv")],
        [InlineKeyboardButton("🚀 Начать рассылку", callback_data="start_send")],
        [InlineKeyboardButton("🔄 Очистить всё", callback_data="clear_all")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])

# ===== ФУНКЦИИ ОТПРАВКИ ЧЕРЕЗ OLX API =====
def get_valid_token(account):
    """Проверяет токен и обновляет если нужно"""
    if not account.get('expires_at'):
        return account.get('access_token')
    
    try:
        expires_at = datetime.fromisoformat(account['expires_at'])
        if datetime.now() >= expires_at:
            # Обновляем токен
            response = requests.post(
                "https://www.olx.ro/api/open/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": account['refresh_token'],
                    "client_id": account.get('client_id', ''),
                    "client_secret": account.get('client_secret', '')
                }
            )
            if response.status_code == 200:
                result = response.json()
                account['access_token'] = result.get('access_token')
                account['refresh_token'] = result.get('refresh_token', account['refresh_token'])
                account['expires_at'] = (datetime.now() + timedelta(seconds=result.get('expires_in', 3600))).isoformat()
                save_data(data)
                return account['access_token']
        return account['access_token']
    except:
        return account.get('access_token')

def send_message_via_api(access_token, ad_id, message_text):
    """Отправляет сообщение в чат объявления"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        # Пробуем отправить сообщение напрямую
        response = requests.post(
            f"https://www.olx.ro/api/partner/ads/{ad_id}/threads",
            headers=headers,
            json={"message": {"text": message_text}}
        )
        if response.status_code == 201:
            return {"success": True}
        elif response.status_code == 409:
            # Чат уже существует — ищем его
            threads = requests.get(
                f"https://www.olx.ro/api/partner/ads/{ad_id}/threads",
                headers=headers
            )
            if threads.status_code == 200:
                thread_data = threads.json()
                if thread_data.get('data') and len(thread_data['data']) > 0:
                    thread_id = thread_data['data'][0].get('id')
                    if thread_id:
                        msg_response = requests.post(
                            f"https://www.olx.ro/api/partner/threads/{thread_id}/messages",
                            headers=headers,
                            json={"text": message_text}
                        )
                        if msg_response.status_code == 201:
                            return {"success": True}
        return {"error": f"Ошибка {response.status_code}: {response.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}

# ===== ОБРАБОТЧИКИ КОМАНД =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>OLX Рассыльщик</b>\n\n"
        "📌 Бот рассылает сообщения в чаты OLX\n\n"
        "1️⃣ Добавьте access_token аккаунтов OLX\n"
        "2️⃣ Загрузите CSV с ID объявлений\n"
        "3️⃣ Добавьте тексты\n"
        "4️⃣ Начните рассылку",
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
            f"👤 Токенов: <b>{len(data['accounts'])}</b>\n"
            f"📝 Текстов: <b>{len(data['texts'])}</b>\n"
            f"📦 Объявлений: <b>{len(data['ads'])}</b>\n"
            f"⏱ Задержка: <b>{data.get('delay', 5)} сек</b>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    # ===== ТОКЕНЫ =====
    elif query.data == "accounts_menu":
        keyboard = [
            [InlineKeyboardButton("➕ Добавить токен", callback_data="add_account")],
            [InlineKeyboardButton("📋 Список токенов", callback_data="list_accounts")],
            [InlineKeyboardButton("🗑️ Удалить токен", callback_data="delete_account")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"👤 <b>Управление токенами</b>\n\n"
            f"Всего: {len(data['accounts'])}\n\n"
            "Введите access_token аккаунта OLX в формате:\n"
            "<code>Название|access_token</code>\n\n"
            "Пример: <code>Мой аккаунт|abc123xyz456</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_account":
        context.user_data['action'] = 'add_account'
        await query.edit_message_text(
            "✏️ <b>Введите токен</b>\n\n"
            "Формат: <code>Название|access_token</code>\n\n"
            "Пример: <code>Аккаунт 1|eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...</code>",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    elif query.data == "list_accounts":
        if not data['accounts']:
            await query.edit_message_text("❌ Нет токенов.", reply_markup=back_button())
            return
        text = ""
        for i, acc in enumerate(data['accounts']):
            token_short = acc['access_token'][:15] + "..." if len(acc['access_token']) > 20 else acc['access_token']
            text += f"{i+1}. {acc.get('name', 'Без имени')}\n   <code>{token_short}</code>\n"
        await query.edit_message_text(f"📋 <b>Токены</b>\n\n{text}", parse_mode='HTML', reply_markup=back_button())
    
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
    
    elif query.data.startswith("del_acc_"):
        idx = int(query.data.split("_")[2])
        data['accounts'].pop(idx)
        save_data(data)
        await query.edit_message_text(f"✅ Токен удалён. Осталось: {len(data['accounts'])}", reply_markup=back_button())
    
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
            "<code>{description}</code> - описание\n"
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
        await query.edit_message_text(f"✅ Текст удалён. Осталось: {len(data['texts'])}", reply_markup=back_button())
    
    # ===== ЗАДЕРЖКА =====
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
            f"⏱ <b>Задержка между сообщениями</b>\n\nТекущая: {data.get('delay', 5)} сек",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("delay_"):
        if query.data == "delay_custom":
            context.user_data['action'] = 'set_delay'
            await query.edit_message_text("✏️ Введите задержку в секундах:", reply_markup=back_button())
        else:
            seconds = int(query.data.split("_")[1])
            data['delay'] = seconds
            save_data(data)
            await query.edit_message_text(f"✅ Задержка: {seconds} сек", reply_markup=main_menu())
    
    # ===== CSV =====
    elif query.data == "upload_csv":
        context.user_data['action'] = 'upload_csv'
        await query.edit_message_text(
            "📤 <b>Загрузка CSV</b>\n\n"
            "Отправьте CSV-файл с объявлениями.\n\n"
            "Формат:\n"
            "<code>ad_id,title,price,city,description,url</code>\n\n"
            "Где ad_id — ID объявления на OLX (для отправки сообщения)",
            parse_mode='HTML',
            reply_markup=back_button()
        )
    
    # ===== РАССЫЛКА =====
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
            f"📦 Объявлений: {len(data['ads'])}\n"
            f"📝 Текстов: {len(data['texts'])}\n"
            f"⏱ Задержка: {data.get('delay', 5)} сек\n\n"
            f"⏳ Пожалуйста, подождите...",
            parse_mode='HTML'
        )
        
        result = await send_all_messages(context, query.from_user.id)
        
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=result,
            parse_mode='HTML',
            reply_markup=main_menu()
        )
    
    elif query.data == "clear_all":
        data['accounts'] = []
        data['texts'] = []
        data['ads'] = []
        data['delay'] = 5
        save_data(data)
        await query.edit_message_text("🔄 <b>Все данные очищены</b>", parse_mode='HTML', reply_markup=main_menu())

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
            # Выбираем случайный токен
            account = random.choice(accounts)
            access_token = account['access_token']
            
            if not access_token:
                errors.append(f"❌ Токен {account.get('name', 'без имени')}: пустой")
                continue
            
            # Выбираем случайный текст
            text_template = random.choice(texts)
            message_text = text_template.format(
                title=ad.get('title', 'Объявление'),
                price=ad.get('price', 'Цена не указана'),
                city=ad.get('city', ''),
                description=ad.get('description', '')[:300],
                url=ad.get('url', '#')
            )
            
            # Отправляем сообщение
            result = send_message_via_api(access_token, ad['ad_id'], message_text)
            
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

# ===== ОБРАБОТЧИК СООБЩЕНИЙ =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    action = user_data.get('action')
    
    if not action:
        await update.message.reply_text("Используйте /start для открытия меню.")
        return
    
    text = update.message.text.strip()
    
    if action == 'add_account':
        # Формат: Название|access_token
        parts = text.split('|')
        if len(parts) >= 2:
            name = parts[0].strip()
            token = parts[1].strip()
            account = {
                "name": name,
                "access_token": token,
                "refresh_token": "",
                "expires_at": ""
            }
            data['accounts'].append(account)
            save_data(data)
            await update.message.reply_text(
                f"✅ <b>Токен добавлен!</b>\n\n"
                f"👤 {name}\n"
                f"🔑 <code>{token[:20]}...{token[-10:]}</code>\n\n"
                f"Всего токенов: <b>{len(data['accounts'])}</b>",
                parse_mode='HTML',
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text(
                "❌ Неправильный формат.\n\n"
                "Используйте: <code>Название|access_token</code>\n"
                "Пример: <code>Мой аккаунт|eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...</code>",
                parse_mode='HTML',
                reply_markup=back_button()
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
    """Парсит CSV в список объявлений"""
    lines = content.strip().split('\n')
    if len(lines) < 2:
        return []
    
    header = lines[0].strip().split(',')
    try:
        ad_id_idx = header.index('ad_id')
        title_idx = header.index('title')
        price_idx = header.index('price') if 'price' in header else None
        city_idx = header.index('city') if 'city' in header else None
        description_idx = header.index('description') if 'description' in header else None
        url_idx = header.index('url') if 'url' in header else None
    except ValueError:
        # Если нет заголовков — по порядку
        return []
    
    ads = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(',')
        ad = {
            'ad_id': parts[ad_id_idx] if ad_id_idx < len(parts) else '',
            'title': parts[title_idx] if title_idx < len(parts) else '',
            'price': parts[price_idx] if price_idx is not None and price_idx < len(parts) else '',
            'city': parts[city_idx] if city_idx is not None and city_idx < len(parts) else '',
            'description': parts[description_idx] if description_idx is not None and description_idx < len(parts) else '',
            'url': parts[url_idx] if url_idx is not None and url_idx < len(parts) else ''
        }
        if ad['ad_id']:
            ads.append(ad)
    return ads

# ===== ЗАПУСК =====
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден в переменных окружения!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_csv_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    import random
    main()