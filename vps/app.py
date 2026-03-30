# vps/app.py
from flask import Flask, render_template, jsonify, request, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta
from functools import wraps
import os
from dotenv import load_dotenv
import database as db

load_dotenv()

app = Flask(__name__)

# 🔐 API Key для аутентификации Raspberry Pi
API_KEY = os.getenv('SCANNER_API_KEY')
if not API_KEY:
    raise ValueError("SCANNER_API_KEY не настроен в .env!")

# 🛡️ Rate limiting для защиты от DDoS
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour", "20 per minute"]
)

# 🔐 Декоратор для проверки API ключа
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        key = request.headers.get('X-API-Key')
        if not key or key != API_KEY:
            abort(403, description="Неверный API ключ")
        return f(*args, **kwargs)
    return decorated_function

# ============================================================
# API для Raspberry Pi (принимает данные)
# ============================================================

@app.route('/api/v1/scan', methods=['POST'])
@require_api_key
@limiter.limit("10 per minute")  # Не чаще 1 раза в 6 секунд
def receive_scan_data():
    """
    Получает данные от Raspberry Pi о текущих MAC-адресах.
    Ожидает JSON: {'macs': ['AA:BB:CC:11:22:33', ...], 'timestamp': '...'}
    """
    data = request.get_json()
    
    if not data or 'macs' not in 
        abort(400, description="Отсутствует поле 'macs'")
    
    macs = [mac.upper() for mac in data.get('macs', [])]
    timestamp = data.get('timestamp', datetime.now().isoformat())
    scanner_id = data.get('scanner_id', 'raspberry-1')
    
    # Сохраняем в БД
    db.save_scan_result(scanner_id, macs, timestamp)
    
    # Проверяем события для уведомлений
    events = db.detect_events(macs)
    
    return jsonify({
        'status': 'ok',
        'received_macs': len(macs),
        'events_detected': len(events),
        'server_time': datetime.now().isoformat()
    })

@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """Проверка доступности API для Raspberry Pi."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

# ============================================================
# Веб-интерфейс (публичный)
# ============================================================

@app.route('/')
def index():
    """Главная страница с визуализацией."""
    current_status = db.get_current_office_status()
    desks = db.get_desks_status()
    
    return render_template('index.html',
                         desks=desks,
                         status=current_status,
                         now=datetime.now())

@app.route('/api/status')
def api_status():
    """API для AJAX-обновления страницы."""
    return jsonify(db.get_current_office_status())

@app.route('/api/events')
def api_events():
    """API для получения последних событий (уведомления)."""
    since = request.args.get('since', datetime.now() - timedelta(minutes=5))
    events = db.get_events(since)
    return jsonify({'events': events})

@app.route('/api/ip')
def get_external_ip():
    """Возвращает внешний IP сервера."""
    try:
        import requests
        ip = requests.get('https://ifconfig.me/ip', timeout=5).text.strip()
        return jsonify({'ip': ip, 'source': 'vps'})
    except:
        return jsonify({'ip': 'не удалось определить', 'source': 'vps'}), 500

# ============================================================
# Админка (защищена паролем)
# ============================================================

@app.route('/admin')
def admin():
    """Панель управления (требует авторизации)."""
    # Простая защита паролем (для продакшена лучше OAuth/JWT)
    if not request.args.get('token') == os.getenv('ADMIN_TOKEN'):
        abort(403, description="Требуется авторизация")
    
    stats = db.get_statistics()
    scanners = db.get_scanner_status()
    
    return render_template('admin.html', stats=stats, scanners=scanners)

# ============================================================
# Обработчики ошибок
# ============================================================

@app.errorhandler(403)
def forbidden(e):
    return jsonify({'error': 'Доступ запрещён', 'detail': str(e)}), 403

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Не найдено'}), 404

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Слишком много запросов', 'retry_after': 60}), 429

if __name__ == '__main__':
    # Инициализация БД
    db.init_database()
    
    # Для продакшена используйте gunicorn + nginx + HTTPS!
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.getenv('FLASK_ENV') == 'development'
    )