# app.py
from flask import Flask, render_template, jsonify
from datetime import datetime
import network_monitor as nm

app = Flask(__name__)

# Конфигурация столов (максимум 4 сотрудника + устройства)
DESKS_CONFIG = [
    {'id': 1, 'name': 'Леха', 'macs_key': 'Леха'},
    {'id': 2, 'name': 'Кирилл', 'macs_key': 'Кирилл'},
    {'id': 3, 'name': 'Макс', 'macs_key': 'Макс'},
    {'id': 4, 'name': 'Коля', 'macs_key': 'Коля'},
]

@app.route('/')
def index():
    """Главная страница с визуализацией."""
    status = nm.get_office_status()
    nm.update_last_visit_if_empty(status['is_empty'])
    
    # Определяем статус для каждого стола
    desks = []
    for desk in DESKS_CONFIG:
        is_present = desk['name'] in status['present']
        desks.append({
            **desk,
            'is_present': is_present,
            'status_class': 'present' if is_present else 'absent'
        })
    
    return render_template('index.html',
                         desks=desks,
                         status=status,
                         now=datetime.now())

@app.route('/api/status')
def api_status():
    """API для AJAX-обновления статуса."""
    status = nm.get_office_status()
    nm.update_last_visit_if_empty(status['is_empty'])
    
    desks = []
    for desk in DESKS_CONFIG:
        desks.append({
            'id': desk['id'],
            'name': desk['name'],
            'is_present': desk['name'] in status['present']
        })
    
    return jsonify({
        'desks': desks,
        'present_count': len(status['present']),
        'guests_count': status['guests_count'],
        'is_empty': status['is_empty'],
        'last_visit': status['last_visit'],
        'timestamp': datetime.now().strftime('%H:%M:%S')
    })

@app.route('/api/ip')
def get_external_ip():
    """Возвращает внешний IP (как в оригинальном боте)."""
    try:
        import requests
        ip = requests.get('https://ifconfig.me/ip', timeout=5).text.strip()
        return jsonify({'ip': ip})
    except:
        return jsonify({'ip': 'не удалось определить'}), 500

if __name__ == '__main__':
    # Запуск только в локальной сети! Для продакшена используйте gunicorn + nginx
    app.run(host='0.0.0.0', port=5000, debug=True)