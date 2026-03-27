// static/script.js

// Обновление времени в реальном времени
function updateTime() {
    const now = new Date();
    document.getElementById('current-date').textContent = 
        now.toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: 'numeric'});
    document.getElementById('current-time').textContent = 
        now.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
}

// Обновление статуса сотрудников через API
async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        // Обновляем столы
        data.desks.forEach(desk => {
            const element = document.getElementById(`desk-${desk.id}`);
            if (element) {
                element.className = `desk ${desk.is_present ? 'present' : 'absent'}`;
                element.querySelector('.desk-status').textContent = 
                    desk.is_present ? '✓ В офисе' : '○ Нет на месте';
            }
        });
        
        // Обновляем статистику
        document.getElementById('present-count').textContent = data.present_count;
        
        // Гости
        const guestsSection = document.getElementById('guests-section');
        if (data.guests_count > 0) {
            guestsSection.innerHTML = `| Гости: ${data.guests_count}`;
            guestsSection.style.display = 'inline';
        } else {
            guestsSection.style.display = 'none';
        }
        
        // Последний визит
        const lastVisitSection = document.getElementById('last-visit-section');
        if (data.is_empty) {
            lastVisitSection.style.display = 'block';
            if (data.last_visit) {
                lastVisitSection.querySelector('strong').textContent = data.last_visit;
            }
        } else {
            lastVisitSection.style.display = 'none';
        }
        
        // Время в футере
        const timeEl = document.querySelector('.auto-update strong');
        if (timeEl) timeEl.textContent = '30 сек';
        
    } catch (error) {
        console.error('Ошибка обновления статуса:', error);
    }
}

// Получение внешнего IP
async function fetchExternalIP() {
    try {
        const response = await fetch('/api/ip');
        const data = await response.json();
        document.getElementById('external-ip').textContent = `IP: ${data.ip}`;
    } catch {
        document.getElementById('external-ip').textContent = 'IP: ошибка';
    }
}

// Экспорт для глобального доступа
window.updateStatus = updateStatus;
window.fetchExternalIP = fetchExternalIP;