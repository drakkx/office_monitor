# vps/database.py
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import json
import os

DB_PATH = 'office_monitor.db'
MACS_DUMP_PATH = '../shared/macs_dump.json'

def get_connection():
    """Создаёт подключение к БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Инициализирует таблицы БД."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Таблица сканов от Raspberry Pi
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanner_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            macs_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица событий (приход/уход)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,  -- arrival, departure, empty, busy
            person_name TEXT,
            mac_address TEXT,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица последнего состояния
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS last_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            macs_json TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def save_scan_result(scanner_id: str, macs: List[str], timestamp: str):
    """Сохраняет результат сканирования от Raspberry Pi."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Сохраняем скан
    cursor.execute('''
        INSERT INTO scans (scanner_id, timestamp, macs_json)
        VALUES (?, ?, ?)
    ''', (scanner_id, timestamp, json.dumps(macs)))
    
    # Обновляем последнее состояние
    cursor.execute('''
        INSERT OR REPLACE INTO last_state (id, macs_json, timestamp)
        VALUES (1, ?, ?)
    ''', (json.dumps(macs), timestamp))
    
    conn.commit()
    conn.close()

def detect_events(current_macs: List[str]) -> List[Dict]:
    """Сравнивает с предыдущим состоянием и обнаруживает события."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Получаем предыдущее состояние
    cursor.execute('SELECT macs_json FROM last_state WHERE id = 1')
    row = cursor.fetchone()
    previous_macs = set(json.loads(row['macs_json'])) if row else set()
    conn.close()
    
    current_set = set(current_macs)
    events = []
    
    # Загружаем известные MAC
    known_macs = load_known_macs()
    
    # Кто пришёл
    for mac in current_set - previous_macs:
        name = get_person_by_mac(mac, known_macs)
        event_type = 'arrival' if name else 'guest_arrival'
        events.append({
            'type': event_type,
            'name': name,
            'mac': mac,
            'timestamp': datetime.now().isoformat()
        })
        save_event(event_type, name, mac)
    
    # Кто ушёл
    for mac in previous_macs - current_set:
        name = get_person_by_mac(mac, known_macs)
        event_type = 'departure' if name else 'guest_departure'
        events.append({
            'type': event_type,
            'name': name,
            'mac': mac,
            'timestamp': datetime.now().isoformat()
        })
        save_event(event_type, name, mac)
    
    # Офис пуст/заполнился
    if not current_set and previous_macs:
        events.append({'type': 'empty', 'timestamp': datetime.now().isoformat()})
        save_event('empty', None, None)
    elif current_set and not previous_macs:
        events.append({'type': 'busy', 'timestamp': datetime.now().isoformat()})
        save_event('busy', None, None)
    
    return events

def save_event(event_type: str, name: Optional[str], mac: Optional[str]):
    """Сохраняет событие в БД."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO events (event_type, person_name, mac_address, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (event_type, name, mac, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_current_office_status() -> Dict:
    """Возвращает текущий статус офиса для веб-интерфейса."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT macs_json, timestamp FROM last_state WHERE id = 1')
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {
            'present': [],
            'present_count': 0,
            'guests_count': 0,  # ✅ Добавлено
            'is_empty': True,
            'last_visit': None,
            'last_update': None,
            'timestamp': datetime.now().isoformat()
        }
    
    current_macs = set(json.loads(row['macs_json']))
    known_macs = load_known_macs()
    total_known_macs = get_all_known_macs(known_macs)  # ✅ Новая функция
    
    present = []
    guests_count = 0
    
    for mac in current_macs:
        name = get_person_by_mac(mac, known_macs)
        if name and name not in present:
            present.append(name)
        elif mac not in total_known_macs:
            guests_count += 1  # ✅ Считаем гостей
    
    # Получаем последнее посещение
    last_visit = get_last_empty_time()
    
    return {
        'present': present,
        'present_count': len(present),
        'guests_count': guests_count,  # ✅ Добавлено
        'is_empty': len(present) == 0,
        'last_visit': last_visit,
        'last_update': row['timestamp'],
        'timestamp': datetime.now().isoformat()
    }

def get_desks_status() -> List[Dict]:
    """Возвращает статус для каждого стола."""
    current_status = get_current_office_status()
    present_names = set(current_status['present'])
    
    # Конфигурация столов (можно вынести в БД)
    desks_config = [
        {'id': 1, 'name': 'Леха'},
        {'id': 2, 'name': 'Кирилл'},
        {'id': 3, 'name': 'Коля'},
        {'id': 4, 'name': 'Макс'},
    ]
    
    return [
        {**desk, 'is_present': desk['name'] in present_names}
        for desk in desks_config
    ]

def get_events(since: datetime = None) -> List[Dict]:
    """Получает события за период."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if since:
        cursor.execute('''
            SELECT * FROM events 
            WHERE created_at > ?
            ORDER BY created_at DESC
            LIMIT 50
        ''', (since.isoformat(),))
    else:
        cursor.execute('''
            SELECT * FROM events 
            ORDER BY created_at DESC 
            LIMIT 50
        ''')
    
    events = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return events

def get_last_empty_time() -> Optional[str]:
    """Получает время последнего опустошения офиса."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp FROM events 
        WHERE event_type = 'empty'
        ORDER BY created_at DESC 
        LIMIT 1
    ''')
    row = cursor.fetchone()
    conn.close()
    return row['timestamp'] if row else None

def get_statistics() -> Dict:
    """Статистика для админки."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM scans')
    total_scans = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM events WHERE event_type = ?', ('arrival',))
    total_arrivals = cursor.fetchone()[0]
    
    cursor.execute('SELECT scanner_id, COUNT(*) as count FROM scans GROUP BY scanner_id')
    scanners = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'total_scans': total_scans,
        'total_arrivals': total_arrivals,
        'scanners': scanners
    }

def get_scanner_status() -> List[Dict]:
    """Статус сканеров (когда последний раз отправляли данные)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT scanner_id, MAX(timestamp) as last_seen, COUNT(*) as scans_count
        FROM scans
        GROUP BY scanner_id
    ''')
    scanners = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return scanners

# ============================================================
# Вспомогательные функции
# ============================================================

def load_known_macs() -> Dict:
    """Загружает базу известных MAC-адресов."""
    if Path(MACS_DUMP_PATH).exists():
        with open(MACS_DUMP_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def get_person_by_mac(mac: str, known_macs: Dict) -> Optional[str]:
    """Находит имя человека по MAC-адресу."""
    for name, mac_list in known_macs.items():
        if mac in mac_list and name != 'Devices':
            return name
    return None

def get_all_known_macs(known_macs: Dict) -> set:
    """Возвращает множество всех известных MAC-адресов (включая Devices)."""
    all_macs = set()
    for name, mac_list in known_macs.items():
        all_macs.update(mac_list)
    return all_macs