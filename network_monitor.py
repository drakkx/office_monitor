# network_monitor.py (дополнение к вашему коду)
import json
from datetime import datetime
from pathlib import Path
import requests
import json
from dotenv import load_dotenv
import os
import subprocess
import re

load_dotenv()

def read_dump(file):
    dump = open(file, "r")
    parsed_dump = json.load(dump)
    dump.close()
    return parsed_dump

def get_active_macs():
    """
    Получает список активных MAC-адресов из ARP-таблицы с помощью 'ip neigh show'.
    Возвращает список строк в формате 'xx:xx:xx:xx:xx:xx'.
    """
    try:
        scan_network_with_nmap()
        # Выполняем команду 'ip neigh show'
        result = subprocess.run(['ip', 'neigh', 'show'],
                                capture_output=True,
                                text=True,
                                check=True)
        output = result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Если команда недоступна (например, на Windows или нет прав)
        return []

    # Регулярное выражение для поиска MAC-адресов вида xx:xx:xx:xx:xx:xx
    mac_pattern = re.compile(r'([0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}')
    macs = mac_pattern.findall(output)

    # findall возвращает кортежи из-за группировки, поэтому извлекаем полные совпадения
    # Лучше использовать finditer или убрать захватывающие скобки
    # Исправим: уберём скобки вокруг повторяющейся части
    mac_pattern_fixed = re.compile(r'(?:[0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}')
    macs = mac_pattern_fixed.findall(output)
    macs_upper = [mac.upper() for mac in macs]
    return macs_upper

def scan_network_with_nmap(subnet="192.168.31.1/24"):
    try:
        result = subprocess.run(
            ["nmap", "-sn", subnet],  # -sn = ping scan (no port scan)
            capture_output=True,
            text=True,
            check=True  # выбросит исключение, если nmap завершится с ошибкой
        )
        return result.stdout
    except FileNotFoundError:
        print("Ошибка: nmap не установлен или не найден в PATH.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"nmap завершился с ошибкой: {e}")
        return None

def get_all_known_macs(dump):
    known_macs_list = []
    for name in dump:
        known_macs_list += dump[name]
    return known_macs_list


def who_is_here_string():
    guests_count = 0
    our_macs = read_dump('macs_dump.json')
    current_macs = get_active_macs()
    response = ''
    checked_names = []
    total_macs_list = get_all_known_macs(our_macs)
    for mac in current_macs:
        for name in our_macs:
            if mac in our_macs[name] and name not in checked_names and name != "Devices":
                checked_names.append(name)
                response += f'{name}\r\n'
    for mac in current_macs:
        if mac not in total_macs_list:
            guests_count += 1
    if response == '':
        response = 'никого, даже '
    return f'Сейчас в офисе..\r\n{response}гостей {str(guests_count)}'

def get_present_people():
    """Возвращает список имён присутствующих сотрудников (без гостей)."""
    our_macs = read_dump('macs_dump.json')
    current_macs = get_active_macs()
    present = []
    seen_names = set()

    for mac in current_macs:
        for name, mac_list in our_macs.items():
            if name == "Devices":
                continue
            if mac in mac_list and name not in seen_names:
                present.append(name)
                seen_names.add(name)
                break  # один MAC — одно имя
    return present

LAST_VISIT_FILE = 'last_visit.json'

def get_office_status():
    """Возвращает детальную информацию о статусе офиса."""
    our_macs = read_dump('macs_dump.json')
    current_macs = get_active_macs()
    total_known = get_all_known_macs(our_macs)
    
    present_people = []
    guests_count = 0
    
    for mac in current_macs:
        found = False
        for name, mac_list in our_macs.items():
            if name != "Devices" and mac in mac_list:
                if name not in present_people:
                    present_people.append(name)
                found = True
                break
        if not found and mac not in total_known:
            guests_count += 1
    
    is_empty = len(present_people) == 0
    last_visit = get_last_visit() if is_empty else None
    
    return {
        'present': present_people,
        'guests_count': guests_count,
        'is_empty': is_empty,
        'last_visit': last_visit,
        'timestamp': datetime.now().isoformat()
    }

def get_last_visit():
    """Читает дату последнего посещения из файла."""
    if Path(LAST_VISIT_FILE).exists():
        with open(LAST_VISIT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('last_empty_time')
    return None

def update_last_visit_if_empty(is_empty: bool):
    """Обновляет время последнего посещения, если офис пуст."""
    if is_empty:
        data = {'last_empty_time': datetime.now().strftime('%d.%m.%Y %H:%M')}
        with open(LAST_VISIT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)