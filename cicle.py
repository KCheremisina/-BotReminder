from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import os

class CyclicEventsScheduler:
    def __init__(self, start_date: datetime):
        self.start_date = start_date
        self.cycle_length = 47
        
        self.events_schedule = {
            1: ("МежОхота", 1, 5, True),
            2: ("Власть", 1, 5, False),
            3: ("Близость", 6, 5, False),
            4: ("Дебаты", 10, 4, False),
            5: ("Знания", 14, 3, False),
            6: ("Гильдия", 14, 5, False),
            7: ("Меж. Ресурсы", 14, 5, True),
            8: ("Слава", 19, 3, False),
            9: ("МежБанкеты", 19, 5, True),
            10: ("МежВласть", 24, 5, True),
            11: ("МежБлизость", 29, 5, True),
            12: ("меж.трата.фруктов", 24, 9, True),
            13: ("Дебаты", 34, 5, False),
            14: ("Междебаты", 39, 4, True),
            15: ("Гильдия", 38, 5, False),
            16: ("Знания", 38, 3, False),
            17: ("Банкеты", 43, 5, False),
            18: ("Слава", 43, 3, False),
            19: ("Возрождение города", 16, 5, True)
        }
        
        for event_num, (name, start_day, duration, is_inter) in self.events_schedule.items():
            end_day = start_day + duration - 1
            if end_day > self.cycle_length:
                print(f"Предупреждение: Событие {event_num} ({name}) выходит за пределы цикла")
    
    def update_messages_config(self, config_path: str = 'messages_config.json'):
        try:
            if not os.path.exists(config_path):
                print(f"❌ Файл {config_path} не найден")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            active_events_today = self.get_active_events_raw()
            print(f"📅 Активные события сегодня: {active_events_today}")
            
            updated_count = 0
            total_event_messages = 0
            
            messages = config.get('messages', [])
            
            for message in messages:
                message_name = message.get('name', '')
                
                if message_name.startswith('event_type_'):
                    total_event_messages += 1
                    
                    try:
                        event_number = int(message_name.replace('event_type_', ''))
                    except ValueError:
                        print(f"⚠️ Не удалось извлечь номер события из имени: {message_name}")
                        continue
                    
                    if event_number in active_events_today:
                        if not message.get('enabled', True):
                            message['enabled'] = True
                            updated_count += 1
                            print(f"✅ Включено: {message.get('description', message_name)} (событие №{event_number})")
                    else:
                        if message.get('enabled', True):
                            message['enabled'] = False
                            updated_count += 1
                            print(f"❌ Отключено: {message.get('description', message_name)} (событие №{event_number})")
            
            if updated_count > 0:
                backup_path = config_path.replace('.json', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
                with open(backup_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                print(f"📦 Создан бэкап: {backup_path}")
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                
                print(f"✅ Конфиг обновлен! Изменено {updated_count} сообщений из {total_event_messages}")
            else:
                print(f"✅ Изменений не требуется. Все {total_event_messages} сообщений уже настроены корректно")
            
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            return False
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            return False
    
    def update_messages_config_for_date(self, target_date: datetime, config_path: str = 'messages_config.json'):
        original_date = datetime.now()
        
        class TempDate:
            def __init__(self, scheduler, temp_date):
                self.scheduler = scheduler
                self.temp_date = temp_date
            
            def __enter__(self):
                self.original_method = self.scheduler.get_active_events_raw
                def temp_get_active():
                    active = []
                    days_diff = (self.temp_date - self.scheduler.start_date).days
                    if days_diff >= 0:
                        position_in_cycle = (days_diff % self.scheduler.cycle_length) + 1
                        for event_num, (_, start_day, duration, _) in self.scheduler.events_schedule.items():
                            end_day = start_day + duration - 1
                            if start_day <= position_in_cycle <= end_day:
                                active.append(event_num)
                    return active
                
                self.scheduler.get_active_events_raw = temp_get_active
                return self.scheduler
            
            def __exit__(self, *args):
                self.scheduler.get_active_events_raw = self.original_method
        
        with TempDate(self, target_date):
            print(f"🔄 Проверка для даты: {target_date.strftime('%d.%m.%Y')}")
            result = self.update_messages_config(config_path)
        
        return result
    
    def debug_messages_config(self, config_path: str = 'messages_config.json'):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            messages = config.get('messages', [])
            
            print("\n🔍 ДИАГНОСТИКА КОНФИГА:")
            print("=" * 50)
            
            event_messages = []
            regular_messages = []
            
            for msg in messages:
                if msg.get('specific_message', False):
                    event_messages.append({
                        'description': msg.get('description'),
                        'event_number': msg.get('event_number'),
                        'enabled': msg.get('enabled')
                    })
                else:
                    regular_messages.append(msg.get('description'))
            
            print(f"📊 Сообщения о событиях ({len(event_messages)}):")
            for msg in event_messages:
                status = "✅" if msg['enabled'] else "❌"
                print(f"  {status} Событие №{msg['event_number']}: {msg['description']}")
            
            print(f"\n📝 Обычные сообщения ({len(regular_messages)}):")
            for desc in regular_messages:
                print(f"  • {desc}")
            
            print("=" * 50)
            
            return event_messages
            
        except Exception as e:
            print(f"❌ Ошибка диагностики: {e}")
            return []

    def auto_update_daily(self, config_path: str = 'messages_config.json'):
        print(f"\n🔄 Автоматическое обновление конфига на {datetime.now().strftime('%d.%m.%Y')}")
        print("=" * 50)
        
        self.debug_messages_config(config_path)
        
        active_events = self.get_active_events_raw()
        print(f"📅 Должны быть активны: {active_events}")
        print(f"📅 Должны быть отключены: {[i for i in range(1, 19) if i not in active_events]}")
        
        return self.update_messages_config(config_path)
    
    def get_active_events(self, target_date: Optional[datetime] = None) -> List[Tuple[int, str, datetime, datetime, bool]]:
        if target_date is None:
            target_date = datetime.now()
        
        days_diff = (target_date - self.start_date).days
        
        if days_diff < 0:
            return []
        
        position_in_cycle = (days_diff % self.cycle_length) + 1
        active_events = []
        
        for event_num, (name, start_day, duration, is_inter) in self.events_schedule.items():
            end_day = start_day + duration - 1
            
            if start_day <= end_day:
                if start_day <= position_in_cycle <= end_day:
                    cycle_start_offset = (days_diff // self.cycle_length) * self.cycle_length
                    event_start_offset = cycle_start_offset + (start_day - 1)
                    event_end_offset = cycle_start_offset + (end_day - 1)
                    
                    event_start = self.start_date + timedelta(days=event_start_offset)
                    event_end = self.start_date + timedelta(days=event_end_offset)
                    
                    active_events.append((event_num, name, event_start, event_end, is_inter))
        
        active_events.sort(key=lambda x: x[0])
        return active_events
    
    def get_active_event_codes(self, target_date: Optional[datetime] = None) -> str:
        active_events = self.get_active_events(target_date)
        
        if not active_events:
            return ""
        
        event_codes = [str(event[0]) for event in active_events]
        return ",".join(event_codes)
    
    def get_active_event_names(self, target_date: Optional[datetime] = None) -> str:
        active_events = self.get_active_events(target_date)
        
        if not active_events:
            return ""
        
        event_names = [event[1] for event in active_events]
        return ",".join(event_names)
    
    def get_active_events_raw(self, target_date: Optional[datetime] = None) -> List[int]:
        active_events = self.get_active_events(target_date)
        return [event[0] for event in active_events]
    
    def format_current_events(self, target_date: Optional[datetime] = None) -> str:
        if target_date is None:
            target_date = datetime.now()
        
        active_events = self.get_active_events(target_date)
        
        if not active_events:
            return f"На {target_date.strftime('%d.%m.%Y')} нет активных событий"
        
        days_diff = (target_date - self.start_date).days
        if days_diff >= 0:
            cycle_num = days_diff // self.cycle_length + 1
            day_in_cycle = (days_diff % self.cycle_length) + 1
            cycle_info = f"Цикл #{cycle_num}, день {day_in_cycle}"
        else:
            cycle_info = "До начала первого цикла"
        
        result = [
            f"Дата: {target_date.strftime('%d.%m.%Y')}",
            f"{cycle_info}",
            f"Активные события ({len(active_events)}):",
            "-" * 40
        ]
        
        for event_num, name, start, end, is_inter in active_events:
            end_time = "22:15" if is_inter else "22:10"
            result.append(
                f"• {name} (№{event_num})\n"
                f"  Период: {start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}\n"
                f"  Время окончания: {end_time}"
            )
        
        return "\n".join(result)
    
    def get_events_calendar(self, cycle_num: int = 1) -> Dict[int, List[str]]:
        calendar = {day: [] for day in range(1, self.cycle_length + 1)}
        
        for event_num, (name, start_day, duration, is_inter) in self.events_schedule.items():
            for day_offset in range(duration):
                day = start_day + day_offset
                if day <= self.cycle_length:
                    calendar[day].append(name)
        
        return calendar
    
    def print_cycle_summary(self):
        print("РАСПИСАНИЕ ЦИКЛА (47 дней)")
        print("=" * 60)
        print(f"Начало первого цикла: {self.start_date.strftime('%d.%m.%Y')}")
        print()
        
        events_by_start = sorted(self.events_schedule.items(), key=lambda x: x[1][1])
        
        for event_num, (name, start_day, duration, is_inter) in events_by_start:
            end_day = start_day + duration - 1
            start_date = self.start_date + timedelta(days=start_day - 1)
            end_date = self.start_date + timedelta(days=end_day - 1)
            end_time = "22:15" if is_inter else "22:00"
            
            print(f"{event_num:2d}. {name:20} "
                  f"Дни {start_day:2d}-{end_day:2d} "
                  f"({start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m')}) "
                  f"время ок.: {end_time}")

if __name__ == "__main__":
    start_date = datetime(2026, 2, 17)
    scheduler = CyclicEventsScheduler(start_date)
    
    scheduler.print_cycle_summary()
    
    print("\n" + "="*60 + "\n")
    
    print("ТЕСТИРОВАНИЕ АВТОМАТИЧЕСКОГО ОБНОВЛЕНИЯ КОНФИГА")
    print("=" * 60)
    
    scheduler.auto_update_daily()
    
    print("\n" + "="*60 + "\n")
    
    test_dates = [
        datetime(2026, 2, 17),
        datetime(2026, 2, 20),
        datetime(2026, 3, 5),
        datetime(2026, 3, 15),
        datetime(2026, 4, 5),
        datetime.now()
    ]
    
    for test_date in test_dates:
        print(f"\nТест для даты: {test_date.strftime('%d.%m.%Y')}")
        print("-" * 40)
        active_raw = scheduler.get_active_events_raw(test_date)
        print(f"Активные события: {active_raw}")
        
        print(f"Должны быть включены события: {active_raw}")
        print(f"Должны быть отключены события: {[i for i in range(1, 19) if i not in active_raw]}")
    
    print("\n" + "="*60)
    print("Пример получения кодов событий на сегодня:")
    print(f"Коды событий на сегодня: {scheduler.get_active_event_codes()}")
    print(f"Названия событий на сегодня: {scheduler.get_active_event_names()}")
    print(f"Список кодов: {scheduler.get_active_events_raw()}")