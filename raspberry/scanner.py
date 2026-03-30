# raspberry/scanner.py
#!/usr/bin/env python3
"""
Сканер сети для Raspberry Pi.
Отправляет данные о MAC-адресах на VPS.
"""

import requests
import subprocess
import re
import json
import time
import os
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# ============================================================
# Конфигурация
# ============================================================

VPS_URL = os.getenv('VPS_URL', 'https://officestatus.ru')
API_KEY = os.getenv('SCANNER_API_KEY')
SCANNER_ID = os.getenv('SCANNER_ID', 'raspberry-1')
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', '30'))  # секунд
SUBNET = os.getenv('OFFICE_SUBNET', '192.168.31.1/24')
LOG_FILE = 'scanner.log'

# ============================================================
# Логирование
# ============================================================

def log(message: str):
    """Пишет лог с временной меткой."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry + '\n')

# ============================================================
# Сканирование сети
# ============================================================

def scan_network() -> list:
    """
    Сканирует локальную сеть и возвращает список активных MAC-адресов.
    """
    log(f"🔍 Начало сканирования сети {SUBNET}...")
    
    try:
        # Шаг 1: Ping-сканирование через nmap для заполнения ARP-таблицы
        subprocess.run(
            ['/usr/bin/nmap', '-sn', SUBNET],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Шаг 2: Чтение ARP-таблицы
        result = subprocess.run(
            ['/usr/sbin/ip', 'neigh', 'show'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Парсинг MAC-адресов
        mac_pattern = re.compile(r'(?:[0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}')
        macs = mac_pattern.findall(result.stdout)
        macs = [mac.upper() for mac in macs]
        
        log(f"✅ Найдено {len(macs)} активных устройств")
        return macs
        
    except subprocess.TimeoutExpired:
        log("❌ Таймаут при сканировании")
        return []
    except FileNotFoundError as e:
        log(f"❌ Команда не найдена: {e}")
        return []
    except Exception as e:
        log(f"❌ Ошибка сканирования: {e}")
        return []

# ============================================================
# Отправка на VPS
# ============================================================

def send_to_vps(macs: list):
    """
    Отправляет данные о MAC-адресах на VPS.
    """
    if not API_KEY:
        log("❌ SCANNER_API_KEY не настроен!")
        return False
    
    payload = {
        'macs': macs,
        'timestamp': datetime.now().isoformat(),
        'scanner_id': SCANNER_ID
    }
    
    headers = {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/11.1.2 Safari/605.1.15'
    }
    
    try:
        response = requests.post(
            f'{VPS_URL}/api/v1/scan',
            json=payload,
            headers=headers,
            timeout=10,
            verify=True  # ✅ Проверка SSL сертификата
        )
        
        if response.status_code == 200:
            data = response.json()
            log(f"📤 Данные отправлены: {data.get('received_macs', 0)} MAC, "
                f"событий: {data.get('events_detected', 0)}")
            return True
        elif response.status_code == 429:
            log("⚠️ Rate limit превышен, пропускаем отправку")
            return False
        else:
            log(f"❌ Ошибка HTTP {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        log("❌ Нет соединения с VPS")
        return False
    except requests.exceptions.Timeout:
        log("❌ Таймаут соединения с VPS")
        return False
    except Exception as e:
        log(f"❌ Ошибка отправки: {e}")
        return False

# ============================================================
# Проверка доступности VPS
# ============================================================

def check_vps_health() -> bool:
    """Проверяет доступность VPS перед началом работы."""
    try:
        response = requests.get(
            f'{VPS_URL}/api/v1/health',
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/11.1.2 Safari/605.1.15'},
            timeout=5,
            verify=True
        )
        if response.status_code == 200:
            log("✅ VPS доступен")
            return True
        else:
            log(f"⚠️ VPS вернул статус {response.status_code}")
            return False
    except Exception as e:
        log(f"❌ VPS недоступен: {e}")
        return False

# ============================================================
# Основной цикл
# ============================================================

def main():
    """Основной цикл сканера."""
    log("🚀 Запуск сканера сети...")
    log(f"📡 VPS: {VPS_URL}")
    log(f"🆔 Scanner ID: {SCANNER_ID}")
    log(f"🔄 Интервал: {SCAN_INTERVAL} сек")
    
    # Проверка доступности VPS при старте
    if not check_vps_health():
        log("⚠️ VPS недоступен, продолжаем с повторными попытками...")
    
    iteration = 0
    while True:
        iteration += 1
        log(f"\n{'='*50}")
        log(f"📊 Итерация #{iteration}")
        
        # Сканирование
        macs = scan_network()
        
        # Отправка на VPS
        if macs or iteration % 10 == 0:  # Отправляем даже пустой результат каждые 10 итераций
            send_to_vps(macs)
            log(f"Отправляем мак-адреса..")
        
        # Ожидание до следующего сканирования
        log(f"😴 Сон на {SCAN_INTERVAL} секунд...")
        time.sleep(SCAN_INTERVAL)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("\n👋 Остановка по сигналу Ctrl+C")
    except Exception as e:
        log(f"💥 Критическая ошибка: {e}")
        raise