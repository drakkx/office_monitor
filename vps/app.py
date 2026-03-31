# vps/app.py
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session, abort
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import database as db
from auth import login_required, admin_required, is_local_ip, generate_csrf_token, validate_csrf_token
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(32).hex())
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True  # Только HTTPS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# API Key для Raspberry Pi
API_KEY = os.getenv('SCANNER_API_KEY')
if not API_KEY:
    raise ValueError("SCANNER_API_KEY не настроен в .env!")

# ============================================================
# Контекстный процессор для шаблонов
# ============================================================

@app.context_processor
def inject_globals():
    """Добавляет переменные во все шаблоны."""
    return {
        'current_user': {
            'id': session.get('user_id'),
            'username': session.get('username'),
            'is_admin': session.get('is_admin', False)
        } if 'user_id' in session else None,
        'csrf_token': generate_csrf_token(),
        'is_local': is_local_ip()
    }

# ============================================================
# Аутентификация
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа."""
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    next_page = request.args.get('next', url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        csrf_token = request.form.get('csrf_token', '')
        
        if not validate_csrf_token(csrf_token):
            flash('⚠️ Ошибка безопасности, попробуйте снова', 'error')
            return render_template('login.html', next=next_page)
        
        user = db.verify_password(username, password)
        
        if user:
            if not user['is_active']:
                flash('🚫 Аккаунт деактивирован', 'error')
                return render_template('login.html', next=next_page)
            
            # Создание сессии
            session_token = db.create_session(
                user['id'],
                request.remote_addr,
                request.headers.get('User-Agent', '')
            )
            
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            session['session_token'] = session_token
            session.permanent = True
            
            flash(f'👋 Добро пожаловать, {user["username"]}!', 'success')
            return redirect(next_page)
        else:
            flash('❌ Неверное имя пользователя или пароль', 'error')
    
    return render_template('login.html', next=next_page)
@app.route('/api/ip')
def get_external_ip():
    """Возвращает внешний IP сервера."""
    try:
        import requests
        # Получаем внешний IP через сторонний сервис
        ip = requests.get('https://ifconfig.me/ip', timeout=5).text.strip()
        return jsonify({'ip': ip, 'source': 'vps'})
    except Exception as e:
        # Логируем ошибку, но возвращаем понятный ответ
        import logging
        logging.warning(f"Не удалось получить внешний IP: {e}")
        return jsonify({'ip': 'не удалось определить', 'source': 'vps', 'error': str(e)}), 200  # ✅ 200, чтобы не было 404/500
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Страница регистрации."""
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    # Регистрация только из локальной сети или для первого пользователя
    if not is_local_ip() and db.get_all_users():
        flash('🚫 Регистрация доступна только из локальной сети', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        csrf_token = request.form.get('csrf_token', '')
        
        if not validate_csrf_token(csrf_token):
            flash('⚠️ Ошибка безопасности', 'error')
            return render_template('register.html')
        
        if password != password_confirm:
            flash('❌ Пароли не совпадают', 'error')
            return render_template('register.html')
        
        # Первый пользователь становится админом
        is_first_user = not db.get_all_users()
        result = db.create_user(username, email, password, is_admin=is_first_user)
        
        if result['success']:
            flash('✅ Регистрация успешна! Теперь войдите', 'success')
            return redirect(url_for('login'))
        else:
            for error in result['errors']:
                flash(f'❌ {error}', 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    """Выход из системы."""
    if 'session_token' in session:
        db.delete_session(session['session_token'])
    session.clear()
    flash('👋 Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Профиль пользователя."""
    if request.method == 'POST':
        action = request.form.get('action')
        csrf_token = request.form.get('csrf_token', '')
        
        if not validate_csrf_token(csrf_token):
            flash('⚠️ Ошибка безопасности', 'error')
            return redirect(url_for('profile'))
        
        if action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            new_password_confirm = request.form.get('new_password_confirm', '')
            
            user = db.get_user_by_id(session['user_id'])
            if not db.check_password_hash(user['password_hash'], current_password):
                flash('❌ Неверный текущий пароль', 'error')
            elif new_password != new_password_confirm:
                flash('❌ Новые пароли не совпадают', 'error')
            else:
                result = db.update_user_password(session['user_id'], new_password)
                if result['success']:
                    flash('✅ Пароль изменён', 'success')
                else:
                    for error in result['errors']:
                        flash(f'❌ {error}', 'error')
    
    return render_template('profile.html')

# ============================================================
# Админка
# ============================================================

@app.route('/admin/users')
@admin_required
def admin_users():
    """Управление пользователями."""
    users = db.get_all_users()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_user(user_id):
    """Активировать/деактивировать пользователя."""
    if user_id == session['user_id']:
        flash('⚠️ Нельзя деактивировать себя', 'warning')
    else:
        user = db.get_user_by_id(user_id)
        if user:
            db.toggle_user_status(user_id, not user['is_active'])
            flash(f'✅ Пользователь {user["username"]} {"активирован" if user["is_active"] == 0 else "деактивирован"}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    """Удалить пользователя."""
    if user_id == session['user_id']:
        flash('⚠️ Нельзя удалить себя', 'warning')
    else:
        if db.delete_user(user_id):
            flash('✅ Пользователь удалён', 'success')
        else:
            flash('⚠️ Нельзя удалить последнего админа', 'error')
    return redirect(url_for('admin_users'))

# ============================================================
# Веб-интерфейс
# ============================================================

@app.route('/')
def index():
    """Главная страница."""
    current_status = db.get_current_office_status()
    desks = db.get_desks_status()
    
    return render_template('index.html',
                         desks=desks,           # ✅ Для первичного рендера
                         status={**current_status, 'desks': desks},  # ✅ Для JS
                         now=datetime.now())

@app.route('/api/status')
def api_status():
    """API для AJAX-обновления страницы."""
    current_status = db.get_current_office_status()
    desks = db.get_desks_status()  # ✅ Получаем статус столов
    
    return jsonify({
        **current_status,  # Распаковываем все поля статуса
        'desks': desks,    # ✅ Добавляем столы
        'timestamp': datetime.now().isoformat()
    })
# ============================================================
# API для Raspberry Pi
# ============================================================

@app.route('/api/v1/scan', methods=['POST'])
def receive_scan_data():
    """Получает данные от Raspberry Pi."""
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    
    key = request.headers.get('X-API-Key')
    if not key or key != API_KEY:
        abort(403, description="Неверный API ключ")
    
    data = request.get_json()
    if not data or 'macs' not in data:
        abort(400, description="Отсутствует поле 'macs'")
    
    macs = [mac.upper() for mac in data.get('macs', [])]
    timestamp = data.get('timestamp', datetime.now().isoformat())
    scanner_id = data.get('scanner_id', 'raspberry-1')
    
    db.save_scan_result(scanner_id, macs, timestamp)
    events = db.detect_events(macs)
    
    return jsonify({
        'status': 'ok',
        'received_macs': len(macs),
        'events_detected': len(events),
        'server_time': datetime.now().isoformat()
    })

@app.route('/api/v1/health')
def health_check():
    """Проверка доступности API."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

# ============================================================
# Обработчики ошибок
# ============================================================

@app.errorhandler(403)
def forbidden(e):
    return jsonify({'error': 'Доступ запрещён'}), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    db.init_database()
    db.cleanup_expired_sessions()
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.getenv('FLASK_ENV') == 'development'
    )