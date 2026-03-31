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
        
        // Проверка успешности запроса
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // ✅ Проверка: существует ли data.desks
        if (data.desks && Array.isArray(data.desks)) {
            // Обновляем столы
            data.desks.forEach(desk => {
                const element = document.getElementById(`desk-${desk.id}`);
                if (element) {
                    element.className = `desk ${desk.is_present ? 'present' : 'absent'}`;
                    
                    const statusEl = element.querySelector('.desk-status');
                    if (statusEl) {
                        statusEl.textContent = desk.is_present 
                            ? '✓ В офисе' 
                            : '○ Нет на месте';
                    }
                }
            });
        } else {
            console.warn('⚠️ data.desks отсутствует или не является массивом');
        }
        
        // Обновляем статистику
        const presentCountEl = document.getElementById('present-count');
        if (presentCountEl && data.present_count !== undefined) {
            presentCountEl.textContent = data.present_count;
        }
        
        // Гости
        const guestsSection = document.getElementById('guests-section');
        if (guestsSection && data.guests_count !== undefined) {
            if (data.guests_count > 0) {
                guestsSection.innerHTML = `| Гости: ${data.guests_count}`;
                guestsSection.style.display = 'inline';
            } else {
                guestsSection.style.display = 'none';
            }
        }
        
        // Последний визит
        const lastVisitSection = document.getElementById('last-visit-section');
        if (lastVisitSection && data.is_empty !== undefined) {
            if (data.is_empty) {
                lastVisitSection.style.display = 'block';
                if (data.last_visit) {
                    const strongEl = lastVisitSection.querySelector('strong');
                    if (strongEl) strongEl.textContent = data.last_visit;
                }
            } else {
                lastVisitSection.style.display = 'none';
            }
        }
        
        // Время обновления
        console.log(`✅ Статус обновлён: ${new Date().toLocaleTimeString()}`);
        
    } catch (error) {
        console.error('❌ Ошибка обновления статуса:', error);
        
        // Визуальное уведомление об ошибке
        const errorToast = document.createElement('div');
        errorToast.className = 'toast toast-error';
        errorToast.innerHTML = `
            <span>⚠️ Не удалось обновить статус</span>
            <button onclick="this.parentElement.remove()">×</button>
        `;
        
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }
        container.appendChild(errorToast);
        
        setTimeout(() => errorToast.remove(), 5000);
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