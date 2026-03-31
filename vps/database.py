# vps/database.py
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = 'office_monitor.db'
MACS_DUMP_PATH = '../shared/macs_dump.json'

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Инициализирует все таблицы БД."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # ===== ТАБЛИЦА ПОЛЬЗОВАТЕЛЕЙ =====
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT,
            login_attempts INTEGER DEFAULT 0,
            locked_until TEXT
        )
    ''')
    
    # ===== ТАБЛИЦА СЕССИЙ =====
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # ===== ТАБЛИЦА СКанов (существующая) =====
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanner_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            macs_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ===== ТАБЛИЦА СОБЫТИЙ (существующая) =====
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            person_name TEXT,
            mac_address TEXT,
            timestamp TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ===== ТАБЛИЦА ПОСЛЕДНЕГО СОСТОЯНИЯ (существующая) =====
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS last_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            macs_json TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ===== Создаём админа по умолчанию =====
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, is_admin, is_active)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin', 'admin@officestatus.ru', 
              generate_password_hash(admin_password), 1, 1))
        print("✅ Создан пользователь admin (смените пароль!)")
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# ============================================================
# Функции управления пользователями
# ============================================================

def create_user(username: str, email: str, password: str, is_admin: bool = False) -> Dict:
    """Создаёт нового пользователя."""
    from auth import validate_username, validate_email, validate_password
    
    # Валидация
    errors = []
    if not validate_username(username):
        errors.append('Неверный формат имени (3-30 символов, буквы, цифры, _ )')
    if not validate_email(email):
        errors.append('Неверный формат email')
    password_errors = validate_password(password)
    errors.extend(password_errors)
    
    if errors:
        return {'success': False, 'errors': errors}
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, is_admin, is_active)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, email.lower(), password_hash, 1 if is_admin else 0, 1))
        conn.commit()
        
        user_id = cursor.lastrowid
        return {'success': True, 'user_id': user_id}
    
    except sqlite3.IntegrityError as e:
        if 'username' in str(e):
            return {'success': False, 'errors': ['Пользователь с таким именем уже существует']}
        elif 'email' in str(e):
            return {'success': False, 'errors': ['Email уже зарегистрирован']}
        return {'success': False, 'errors': ['Ошибка при создании пользователя']}
    finally:
        conn.close()

def get_user_by_username(username: str) -> Optional[Dict]:
    """Получает пользователя по имени."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Получает пользователя по ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def verify_password(username: str, password: str) -> Optional[Dict]:
    """Проверяет пароль и возвращает пользователя если успешно."""
    user = get_user_by_username(username)
    if not user:
        return None
    
    # Проверка блокировки
    if user['locked_until']:
        locked_until = datetime.fromisoformat(user['locked_until'])
        if datetime.now() < locked_until:
            return None  # Аккаунт заблокирован
        else:
            # Сброс блокировки
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET locked_until = NULL, login_attempts = 0 WHERE id = ?', (user['id'],))
            conn.commit()
            conn.close()
            user = get_user_by_username(username)
    
    if check_password_hash(user['password_hash'], password):
        # Успешный вход — сброс попыток
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET login_attempts = 0, locked_until = NULL, last_login = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), user['id']))
        conn.commit()
        conn.close()
        
        return user
    else:
        # Неудачная попытка
        conn = get_connection()
        cursor = conn.cursor()
        new_attempts = user['login_attempts'] + 1
        
        if new_attempts >= 5:
            # Блокировка на 15 минут
            locked_until = (datetime.now() + timedelta(minutes=15)).isoformat()
            cursor.execute('''
                UPDATE users 
                SET login_attempts = ?, locked_until = ?
                WHERE id = ?
            ''', (new_attempts, locked_until, user['id']))
        else:
            cursor.execute('''
                UPDATE users 
                SET login_attempts = ?
                WHERE id = ?
            ''', (new_attempts, user['id']))
        
        conn.commit()
        conn.close()
        return None

def get_all_users() -> List[Dict]:
    """Получает всех пользователей (для админки)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, is_admin, is_active, created_at, last_login FROM users ORDER BY id')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users

def delete_user(user_id: int) -> bool:
    """Удаляет пользователя (кроме последнего админа)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Проверка: не последний ли админ
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1 AND id != ?', (user_id,))
    if cursor.fetchone()[0] == 0:
        conn.close()
        return False  # Нельзя удалить последнего админа
    
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return True

def toggle_user_status(user_id: int, is_active: bool) -> bool:
    """Активирует/деактивирует пользователя."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = ? WHERE id = ?', (1 if is_active else 0, user_id))
    conn.commit()
    conn.close()
    return True

def update_user_password(user_id: int, new_password: str) -> Dict:
    """Обновляет пароль пользователя."""
    from auth import validate_password
    
    errors = validate_password(new_password)
    if errors:
        return {'success': False, 'errors': errors}
    
    conn = get_connection()
    cursor = conn.cursor()
    password_hash = generate_password_hash(new_password, method='pbkdf2:sha256', salt_length=16)
    cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
    conn.commit()
    conn.close()
    
    return {'success': True}

# ============================================================
# Функции сессий
# ============================================================

def create_session(user_id: int, ip_address: str, user_agent: str) -> str:
    """Создаёт новую сессию и возвращает токен."""
    import secrets
    
    session_token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=7)).isoformat()
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sessions (user_id, session_token, expires_at, ip_address, user_agent)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, session_token, expires_at, ip_address, user_agent))
    conn.commit()
    conn.close()
    
    return session_token

def get_session_by_token(session_token: str) -> Optional[Dict]:
    """Получает сессию по токену."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, u.username, u.is_admin 
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_token = ? AND s.expires_at > ?
    ''', (session_token, datetime.now().isoformat()))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_session(session_token: str):
    """Удаляет сессию (logout)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sessions WHERE session_token = ?', (session_token,))
    conn.commit()
    conn.close()

def cleanup_expired_sessions():
    """Удаляет просроченные сессии."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sessions WHERE expires_at < ?', (datetime.now().isoformat(),))
    conn.commit()
    conn.close()

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

def get_desks_config() -> List[Dict]:
    """
    Генерирует конфигурацию столов из macs_dump.json.
    Возвращает список: [{'id': 1, 'name': 'Alexey', 'macs': [...]}, ...]
    """
    known_macs = load_known_macs()
    
    desks = []
    desk_id = 1
    
    # Сортируем имена для стабильного порядка
    for name in sorted(known_macs.keys()):
        # Пропускаем служебные записи
        if name in ['Devices', 'devices', 'DEVICES']:
            continue
        if name.startswith('Guest_') or name.startswith('guest_'):
            continue
        if '_' in name and not name.replace('_', '').isalnum():
            continue
            
        desks.append({
            'id': desk_id,
            'name': name,
            'macs': known_macs[name]
        })
        desk_id += 1
    
    return desks

def get_desks_status() -> List[Dict]:
    """
    Возвращает статус для каждого динамического стола.
    """
    desks_config = get_desks_config()
    current_status = get_current_office_status()
    present_names = set(current_status['present'])
    
    return [
        {
            'id': desk['id'],
            'name': desk['name'],
            'is_present': desk['name'] in present_names,
            'macs': desk['macs']  # Можно использовать для отладки
        }
        for desk in desks_config
    ]

def get_total_desks_count() -> int:
    """Возвращает общее количество столов."""
    return len(get_desks_config())

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