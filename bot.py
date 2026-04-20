import asyncio
from datetime import time, datetime, timedelta
import pytz
from telegram import Bot
from telegram.ext import Application, CommandHandler
from config import TOKEN, CHAT_ID, USER_ID, MESSAGES, scheduler, PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD, MTPROTO_SECRET  
from cicle import CyclicEventsScheduler
from proxy_manager import get_proxy_manager, ProxyManager
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

moscow_tz = pytz.timezone('Europe/Moscow')

message_status = {msg['name']: msg['enabled'] for msg in MESSAGES}

def get_message_by_name(name):
    for msg in MESSAGES:
        if msg['name'] == name:
            return msg
    return None

def format_events_info(active_events):
    if not active_events:
        return "❌ Нет активных событий на сегодня"
    
    now = datetime.now(moscow_tz)
    today = now.date()
    
    result = []
    for event_num, name, start, end, is_inter in active_events:
        if end.tzinfo is None:
            end = moscow_tz.localize(end)
        
        end_time_base = "22:15" if is_inter else "22:00"
        end_hour = int(end_time_base.split(':')[0])
        end_minute = int(end_time_base.split(':')[1]) - 30
        if end_minute < 0:
            end_hour -= 1
            end_minute += 60
        end_time = f"{end_hour:02d}:{end_minute:02d}"
        
        end_date = end.date()
        days_left = (end_date - today).days
        
        if days_left == 0:
            time_left = "последний день!"
        elif days_left == 1:
            time_left = "остался 1 день"
        elif days_left > 1:
            time_left = f"осталось {days_left} дней"
        else:
            time_left = "завершилось"
        
        result.append(
            f"🔸 {name} (№{event_num})\n"
            f"   Период: {start.strftime('%d.%m')} - {end.strftime('%d.%m')}\n"
            f"   Окончание: {end_time}, {time_left}"
        )
    
    return "\n".join(result)

def get_event_codes_string():
    codes = scheduler.get_active_event_codes()
    if codes:
        return f"🔢 Коды событий: {codes}"
    return ""

def check_new_events_start_today():
    active_events = scheduler.get_active_events()
    today = datetime.now(moscow_tz).date()
    
    new_events = []
    for event in active_events:
        event_num, name, start, end, is_inter = event
        if start.date() == today:
            new_events.append(name)
    
    return new_events

def get_event_specific_info(event_num, event_name, event_end, is_inter):
    if event_end.tzinfo is None:
        event_end = moscow_tz.localize(event_end)
    
    end_time_base = "22:15" if is_inter else "22:00"
    end_hour = int(end_time_base.split(':')[0])
    end_minute = int(end_time_base.split(':')[1]) - 30
    if end_minute < 0:
        end_hour -= 1
        end_minute += 60
    event_end_time = f"{end_hour:02d}:{end_minute:02d}"
    
    now = datetime.now(moscow_tz)
    time_left = event_end - now
    
    if time_left.total_seconds() <= 0:
        time_left_str = "завершилось"
    elif time_left.days > 0:
        time_left_str = f"{time_left.days} дн {time_left.seconds//3600} ч"
    elif time_left.seconds > 3600:
        time_left_str = f"{time_left.seconds//3600} ч {(time_left.seconds%3600)//60} мин"
    elif time_left.seconds > 0:
        time_left_str = f"{time_left.seconds//60} мин"
    else:
        time_left_str = "менее минуты"
    
    return {
        'event_name': event_name,
        'event_code': str(event_num),
        'event_end_date': event_end.strftime('%d.%m.%Y'),
        'event_end_time': event_end_time,
        'time_left': time_left_str
    }

async def send_scheduled_message(context):
    job_data = context.job.data
    message_name = job_data['name']
    message_config = get_message_by_name(message_name)
    
    if not message_config:
        print(f"Ошибка: сообщение {message_name} не найдено в конфигурации")
        return
    
    if not message_status.get(message_name, False):
        print(f"Сообщение {message_config['description']} отключено")
        return
    
    now = datetime.now(moscow_tz)
    current_weekday = now.weekday()
    
    allowed_days = message_config.get('days', [])
    
    weekdays_ru = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    current_weekday_ru = weekdays_ru[current_weekday]
    
    print(f"\n📅 ПРОВЕРКА ДНЯ ДЛЯ {message_config['description']}:")
    print(f"  • Сегодня: {current_weekday} ({current_weekday_ru})")
    print(f"  • Разрешённые дни: {allowed_days}")
    print(f"  • Соответствует? {current_weekday in allowed_days if allowed_days else 'Нет ограничений'}")
    
    if allowed_days and current_weekday not in allowed_days:
        print(f"  ⏭️ СООБЩЕНИЕ ПРОПУЩЕНО: сегодня {current_weekday_ru} не в списке разрешённых дней")
        return
    
    print(f"  ✅ СООБЩЕНИЕ БУДЕТ ОТПРАВЛЕНО: сегодня {current_weekday_ru} в списке разрешённых дней")
    
    active_events = scheduler.get_active_events()
    today = now.date()
    
    extra_text = message_config.get('extra_text', '')
    if extra_text:
        extra_text = f"\n\n{extra_text}"
        print(f"📝 Добавлен дополнительный текст для {message_config['description']}")
    
    message_name_lower = message_config['name'].lower()
    is_morning = 'morning' in message_name_lower
    is_evening = 'evening' in message_name_lower
    is_regular_event = (message_config.get('specific_message', False) or 
                       message_config['name'].startswith('event_type_'))
    
    if is_morning or is_evening or is_regular_event:
        
        event_number = None
        
        if message_config.get('specific_message', False):
            event_number = message_config.get('event_number')
        
        elif message_config['name'].startswith('event_type_'):
            try:
                import re
                match = re.search(r'event_type_(\d+)', message_config['name'])
                if match:
                    event_number = int(match.group(1))
            except:
                print(f"Не удалось извлечь номер события из имени: {message_config['name']}")
                return
        
        if event_number is None:
            print(f"Не удалось определить номер события для {message_config['name']}")
            return
        
        target_event = None
        for event in active_events:
            if event[0] == event_number:
                target_event = event
                break
        
        if not target_event:
            print(f"Событие №{event_number} не активно сегодня, сообщение не отправлено")
            return
        
        event_num, name, start, end, is_inter = target_event
        
        if end.tzinfo is None:
            end = moscow_tz.localize(end)
        
        end_date = end.date()
        
        print(f"📅 Событие {name} (№{event_num}):")
        print(f"  Дата окончания: {end_date}")
        print(f"  Сегодня: {today}")
        print(f"  Тип сообщения: {message_config['name']}")
        
        if is_morning or is_evening:
            print(f"✅ Это {'утреннее' if is_morning else 'вечернее'} напоминание. Событие активно сегодня, отправляю...")
            
        else:
            if end_date != today:
                days_left = (end_date - today).days
                print(f"⏳ Событие №{event_number} заканчивается {end_date.strftime('%d.%m.%Y')} (через {days_left} дн). Это не последний день, сообщение не отправлено.")
                return
            print(f"✅ СЕГОДНЯ ПОСЛЕДНИЙ ДЕНЬ! Отправляю сообщение {message_config['description']}")
        
        event_info = get_event_specific_info(
            event_num, name, end, is_inter
        )
        
        if is_morning:
            event_info['time_of_day'] = 'утро'
            prefix = "🌅 ДОБРОЕ УТРО! "
        elif is_evening:
            event_info['time_of_day'] = 'вечер'
            prefix = "🌙 ВЕЧЕРНЕЕ НАПОМИНАНИЕ! "
        else:
            event_info['time_of_day'] = ''
            prefix = "⚠️ "
        
        try:
            base_message = message_config['text'].format(**event_info)
        except KeyError as e:
            print(f"Ошибка форматирования: {e}")
            base_message = message_config['text']
        
        if prefix and prefix not in base_message:
            base_message = prefix + base_message
        
        message = base_message + extra_text
            
    else:
        events_info = format_events_info(active_events)
        event_codes_info = get_event_codes_string()
        
        current_time = now.strftime("%H:%M:%S")
        current_date = now.strftime("%d.%m.%Y")
        weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
        today_weekday = weekdays[now.weekday()]
        
        try:
            base_message = message_config['text'].format(
                current_date=current_date,
                current_time=current_time,
                today_weekday=today_weekday,
                events_info=events_info,
                event_codes_info=event_codes_info
            )
        except KeyError:
            base_message = message_config['text']
        
        message = base_message + extra_text
    
    await context.bot.send_message(chat_id=CHAT_ID, text=message)
    print(f"[{now.strftime('%d.%m.%Y %H:%M:%S')}] {message_config['description']} отправлено")
    
    if USER_ID:
        try:
            user_message = f"📋 Копия сообщения из беседы:\n\n{message}"
            await context.bot.send_message(chat_id=USER_ID, text=user_message)
            print(f"✅ Копия отправлена пользователю {USER_ID}")
        except Exception as e:
            print(f"❌ Ошибка при отправке пользователю {USER_ID}: {e}")
    
    if message_name == "event_start_notification":
        new_events = check_new_events_start_today()
        if new_events:
            print(f"Сегодня начинаются новые события: {', '.join(new_events)}")

async def start_command(update, context):
    chat_id = update.effective_chat.id
    current_time = datetime.now(moscow_tz).strftime("%H:%M:%S")
    
    active_events = scheduler.get_active_events()
    events_info = format_events_info(active_events)
    event_codes = scheduler.get_active_event_codes()
    
    schedule_text = ""
    for msg in MESSAGES:
        days_text = []
        day_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
        for day in msg['days']:
            days_text.append(day_names[day])
        
        if len(msg['days']) == 7:
            days_str = "ежедневно"
        else:
            days_str = ", ".join(days_text)
        
        status = "✅" if message_status[msg['name']] else "❌"
        schedule_text += f"  • {status} {msg['description']}: {msg['hour']:02d}:{msg['minute']:02d} ({days_str})\n"
    
    response = (
        f"✅ Бот запущен!\n"
        f"🆔 ID чата: {chat_id}\n"
        f"📍 Часовой пояс: Москва (МСК)\n"
        f"⏰ Текущее время: {current_time}\n\n"
        f"📊 СОБЫТИЯ НА СЕГОДНЯ:\n{events_info}\n"
    )
    
    if event_codes:
        response += f"\n🔢 Коды событий: {event_codes}\n"
    
    response += f"\n📅 Расписание уведомлений:\n{schedule_text}\n"
    response += f"Для изменения настроек отредактируйте файл messages_config.json\n"
    response += f"\n📋 Доступные команды:\n"
    response += f"  /gimmeinfo - показать сегодняшние события\n"
    response += f"  /status - статус всех сообщений\n"
    response += f"  /events [дата] - информация о событиях\n"
    response += f"  /reload - перезагрузить конфигурацию"
    
    await update.message.reply_text(response)

async def status_command(update, context):
    status_text = "📊 СТАТУС СООБЩЕНИЙ:\n\n"
    
    for msg in MESSAGES:
        status = "✅ ВКЛЮЧЕНО" if message_status[msg['name']] else "❌ ВЫКЛЮЧЕНО"
        status_text += f"{msg['description']}: {status}\n"
    
    active_events = scheduler.get_active_events()
    event_codes = scheduler.get_active_event_codes()
    
    status_text += f"\n📅 АКТИВНЫЕ СОБЫТИЯ:\n"
    status_text += format_events_info(active_events)
    
    if event_codes:
        status_text += f"\n\n🔢 Коды событий: {event_codes}"
    
    now = datetime.now(moscow_tz)
    start_date = scheduler.start_date
    if start_date.tzinfo is None:
        start_date = moscow_tz.localize(start_date)
    
    days_diff = (now - start_date).days
    if days_diff >= 0:
        cycle_num = days_diff // scheduler.cycle_length + 1
        day_in_cycle = (days_diff % scheduler.cycle_length) + 1
        status_text += f"\n\n📌 Цикл #{cycle_num}, день {day_in_cycle}"
    
    await update.message.reply_text(status_text)

async def events_command(update, context):
    args = context.args
    if args:
        try:
            target_date = datetime.strptime(args[0], '%Y-%m-%d')
            target_date = moscow_tz.localize(target_date)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД")
            return
    else:
        target_date = datetime.now(moscow_tz)
    
    events_info = scheduler.format_current_events(target_date)
    event_codes = scheduler.get_active_event_codes(target_date)
    
    response = events_info
    if event_codes:
        response += f"\n\n🔢 Коды событий: {event_codes}"
    
    await update.message.reply_text(response)

async def gimmeinfo_command(update, context):
    current_time = datetime.now(moscow_tz).strftime("%H:%M:%S")
    current_date = datetime.now(moscow_tz).strftime("%d.%m.%Y")
    
    active_events = scheduler.get_active_events()
    
    if not active_events:
        response = f"📅 {current_date} {current_time}\n\n❌ Сегодня нет активных событий"
        await update.message.reply_text(response)
        return
    
    events_info = format_events_info(active_events)
    event_codes = scheduler.get_active_event_codes()
    
    now = datetime.now(moscow_tz)
    start_date = scheduler.start_date
    if start_date.tzinfo is None:
        start_date = moscow_tz.localize(start_date)
    
    days_diff = (now - start_date).days
    cycle_num = days_diff // scheduler.cycle_length + 1
    day_in_cycle = (days_diff % scheduler.cycle_length) + 1
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    today_weekday = weekdays[now.weekday()]
    
    end_time = "22:10"
    for event in active_events:
        if event[4]:
            end_time = "22:15"
            break
    
    end_hour = int(end_time.split(':')[0])
    end_minute = int(end_time.split(':')[1]) - 30
    if end_minute < 0:
        end_hour -= 1
        end_minute += 60
    end_time_adjusted = f"{end_hour:02d}:{end_minute:02d}"
    
    response = (
        f"📅 ИНФОРМАЦИЯ О СОБЫТИЯХ\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📆 Дата: {current_date}\n"
        f"📅 День недели: {today_weekday}\n"
        f"⏰ Время: {current_time}\n"
        f"🔄 Цикл: #{cycle_num}, день {day_in_cycle}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{events_info}\n\n"
        f"🔢 Коды событий: {event_codes}\n"
        f"⏱️ События заканчиваются в {end_time_adjusted} (за 30 мин до {end_time})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Всего активно: {len(active_events)} событий"
    )
    
    await update.message.reply_text(response)

async def reload_command(update, context):
    try:
        from config import load_config
        new_config = load_config()
        
        global message_status
        new_messages = new_config['messages']
        message_status = {msg['name']: msg['enabled'] for msg in new_messages}
        
        await update.message.reply_text("✅ Конфигурация успешно перезагружена!")
        print("Конфигурация перезагружена по команде /reload")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при перезагрузке: {str(e)}")

async def check_proxy_command(update, context):
    proxy_manager = get_proxy_manager()
    
    if not proxy_manager.is_configured():
        await update.message.reply_text("ℹ️ Прокси не настроен. Бот работает напрямую.")
        return
    
    proxy_info = proxy_manager.get_proxy_info()
    status_text = f"🔧 **Информация о прокси**\n\n"
    status_text += f"📡 URL: `{proxy_info['url']}`\n"
    status_text += f"🔐 Аутентификация: {'Да' if proxy_info['has_auth'] else 'Нет'}\n\n"
    
    await update.message.reply_text(status_text, parse_mode='Markdown')
    
    await update.message.reply_text("🔄 Проверка соединения через прокси...")
    success, message = await proxy_manager.test_connection()
    
    if success:
        await update.message.reply_text(f"✅ {message}")
    else:
        await update.message.reply_text(f"❌ {message}")

async def set_proxy_command(update, context):
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Использование: `/set_proxy <proxy_url> [username] [password]`\n\n"
            "Примеры:\n"
            "  `/set_proxy socks5://127.0.0.1:9050`\n"
            "  `/set_proxy http://user:pass@proxy.com:8080`",
            parse_mode='Markdown'
        )
        return
    
    proxy_url = args[0]
    proxy_username = args[1] if len(args) > 1 else None
    proxy_password = args[2] if len(args) > 2 else None
    
    global PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD
    PROXY_URL = proxy_url
    PROXY_USERNAME = proxy_username
    PROXY_PASSWORD = proxy_password
    
    from proxy_manager import reset_proxy_manager
    reset_proxy_manager()
    proxy_manager = get_proxy_manager(proxy_url, proxy_username, proxy_password)
    
    proxy_manager.create_client()
    
    success, message = await proxy_manager.test_connection()
    
    if success:
        await update.message.reply_text(
            f"✅ Прокси настроен и работает!\n"
            f"📡 URL: {proxy_manager._mask_url(proxy_url)}\n"
            f"🔐 Аутентификация: {'Да' if proxy_username else 'Нет'}\n\n"
            f"⚠️ Для применения изменений требуется перезапуск бота."
        )
    else:
        await update.message.reply_text(f"❌ Прокси настроен, но не работает: {message}")

def create_application_with_proxy():
    from config import TOKEN, PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD, PROXY_TYPE, MTPROTO_SECRET
    from proxy_manager import get_proxy_manager
    
    proxy_manager = get_proxy_manager(
        PROXY_URL, 
        PROXY_USERNAME, 
        PROXY_PASSWORD,
        PROXY_TYPE,
        MTPROTO_SECRET
    )
    
    application = proxy_manager.create_application(TOKEN)
    
    return application, proxy_manager

def create_application_with_proxy():
    from config import TOKEN, PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD, PROXY_TYPE, MTPROTO_SECRET
    from proxy_manager import get_proxy_manager
    
    proxy_manager = get_proxy_manager(
        PROXY_URL, 
        PROXY_USERNAME, 
        PROXY_PASSWORD,
        PROXY_TYPE,
        MTPROTO_SECRET
    )
    
    application = proxy_manager.create_application(TOKEN)
    
    return application, proxy_manager

async def test_mtproto_command(update, context):
    from config import TOKEN, PROXY_URL, PROXY_TYPE, MTPROTO_SECRET
    from proxy_manager import get_proxy_manager
    
    proxy_manager = get_proxy_manager(
        PROXY_URL, 
        PROXY_USERNAME, 
        PROXY_PASSWORD,
        PROXY_TYPE,
        MTPROTO_SECRET
    )
    
    if not proxy_manager.is_configured():
        await update.message.reply_text("❌ Прокси не настроен")
        return
    
    if PROXY_TYPE != 'mtproto':
        await update.message.reply_text("ℹ️ Это не MTProto прокси, используйте /checkproxy")
        return
    
    await update.message.reply_text("🔄 Тестирую MTProto прокси...")
    success, message = await proxy_manager.test_mtproto_connection(TOKEN)
    
    if success:
        await update.message.reply_text(f"✅ {message}")
    else:
        await update.message.reply_text(f"❌ {message}")

def main():
    print("\n" + "="*50)
    print("🤖 ЗАПУСК БОТА")
    print("="*50)
    
    from config import PROXY_URL, PROXY_TYPE, TOKEN
    from proxy_manager import get_proxy_manager
    
    proxy_manager = get_proxy_manager(PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD, PROXY_TYPE, MTPROTO_SECRET)
    
    if proxy_manager.is_configured():
        print(f"\n🔧 Настройки прокси:")
        print(f"   Тип: {PROXY_TYPE}")
        print(f"   URL: {proxy_manager._mask_url(PROXY_URL)}")
        print(f"   Аутентификация: {'Да' if PROXY_USERNAME else 'Нет'}")
        print(f"   MTProto секрет: {'Да' if MTPROTO_SECRET else 'Нет'}")
        
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if PROXY_TYPE == 'mtproto':
                success, message = loop.run_until_complete(
                    proxy_manager.test_mtproto_connection(TOKEN)
                )
            else:
                success, message = loop.run_until_complete(
                    proxy_manager.test_connection()
                )
            
            if success:
                print(f"   ✅ {message}")
            else:
                print(f"   ⚠️ {message}")
                
            loop.close()
        except Exception as e:
            print(f"   ⚠️ Не удалось протестировать прокси: {e}")
    else:
        print("\nℹ️ Прокси не настроен, работаем напрямую")
    
    application, proxy_manager = create_application_with_proxy()
    
    application.add_handler(CommandHandler("testmtproto", test_mtproto_command))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CommandHandler("gimmeinfo", gimmeinfo_command))
    application.add_handler(CommandHandler("reload", reload_command))
    application.add_handler(CommandHandler("checkproxy", check_proxy_command))
    application.add_handler(CommandHandler("set_proxy", set_proxy_command))
    
    job_queue = application.job_queue
    
    async def daily_config_update(context):
        print(f"🔄 Ежедневное обновление конфига в {datetime.now(moscow_tz).strftime('%H:%M:%S')}")
        try:
            scheduler.auto_update_daily('messages_config.json')
            print("✅ Конфиг успешно обновлен")
        except Exception as e:
            print(f"❌ Ошибка при обновлении конфига: {e}")
    
    job_queue.run_daily(
        daily_config_update,
        time=time(hour=0, minute=1, second=0, tzinfo=moscow_tz),
        days=tuple(range(7))
    )
    
    for msg_config in MESSAGES:
        if msg_config.get('enabled', True):
            job_queue.run_daily(
                send_scheduled_message,
                time=time(
                    hour=msg_config['hour'],
                    minute=msg_config['minute'],
                    second=msg_config.get('second', 0),
                    tzinfo=moscow_tz
                ),
                days=tuple(msg_config.get('days', [0,1,2,3,4,5,6])),
                data={'name': msg_config['name']}
            )
            print(f"   • {msg_config['description']}: {msg_config['hour']:02d}:{msg_config['minute']:02d} (ВКЛЮЧЕНО)")
        else:
            print(f"   ⏭️ {msg_config['description']}: пропущено (ОТКЛЮЧЕНО)")
    
    active_events = scheduler.get_active_events()
    event_codes = scheduler.get_active_event_codes()
    
    now = datetime.now(moscow_tz)
    start_date = scheduler.start_date
    if start_date.tzinfo is None:
        start_date = moscow_tz.localize(start_date)
    
    days_diff = (now - start_date).days
    cycle_num = days_diff // scheduler.cycle_length + 1
    day_in_cycle = (days_diff % scheduler.cycle_length) + 1
    
    print(f"\n🤖 Бот запущен!")
    print(f"🕒 Текущее московское время: {datetime.now(moscow_tz).strftime('%H:%M:%S')}")
    print(f"🔄 Текущий цикл: #{cycle_num}, день {day_in_cycle}")
    print(f"📅 Активные события на сегодня:")
    print(format_events_info(active_events))
    if event_codes:
        print(f"🔢 Коды событий: {event_codes}")
    
    print("\n" + "="*50)
    print("✅ БОТ ГОТОВ К РАБОТЕ")
    print("="*50 + "\n")
    
    application.run_polling()

if __name__ == '__main__':
    main()