# vps/auth.py
from functools import wraps
from flask import session, redirect, url_for, request, flash
import re
import ipaddress

# ============================================================
# Валидация
# ============================================================

def validate_username(username: str) -> bool:
    """Проверяет имя пользователя (3-30 символов, буквы, цифры, _)."""
    return bool(re.match(r'^[a-zA-Z0-9_]{3,30}$', username))

def validate_email(email: str) -> bool:
    """Проверяет email."""
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))

def validate_password(password: str) -> list:
    """Проверяет сложность пароля. Возвращает список ошибок."""
    errors = []
    if len(password) < 8:
        errors.append('Минимум 8 символов')
    if len(password) > 128:
        errors.append('Максимум 128 символов')
    if not re.search(r'[A-Z]', password):
        errors.append('Хотя бы одна заглавная буква')
    if not re.search(r'[a-z]', password):
        errors.append('Хотя бы одна строчная буква')
    if not re.search(r'\d', password):
        errors.append('Хотя бы одна цифра')
    return errors

# ============================================================
# Декораторы
# ============================================================

def login_required(f):
    """Требует авторизацию пользователя."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('🔐 Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Требует права администратора."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('🔐 Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login', next=request.url))
        if not session.get('is_admin'):
            flash('⛔ Недостаточно прав', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def is_local_ip() -> bool:
    """Проверяет, является ли IP локальным."""
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    local_networks = ['192.168.0.0/16', '10.0.0.0/8', '172.16.0.0/12', '127.0.0.0/8']
    try:
        for network in local_networks:
            if ipaddress.ip_address(client_ip) in ipaddress.ip_network(network):
                return True
    except ValueError:
        pass
    return False

# ============================================================
# CSRF Token
# ============================================================

import secrets

def generate_csrf_token() -> str:
    """Генерирует CSRF токен для формы."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

def validate_csrf_token(token: str) -> bool:
    """Проверяет CSRF токен."""
    return token and token == session.get('_csrf_token')