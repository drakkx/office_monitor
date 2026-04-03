// static/script.js
function updateTime() {
    const now = new Date();
    document.getElementById('current-date').textContent = 
        now.toLocaleDateString('ru-RU', {day: '2-digit', month: '2-digit', year: 'numeric'});
    document.getElementById('current-time').textContent = 
        now.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
}

// 🆕 Получаем количество столов из конфигурации
function getDesksCount() {
    return window.DESKS_CONFIG?.total || 
           document.getElementById('desks-container')?.dataset.total || 
           4;  // Fallback
}

// 🆕 Ждём появления всех динамических столов
async function waitForDesks(timeout = 5000) {
    return new Promise((resolve, reject) => {
        const startTime = Date.now();
        
        const check = () => {
            const total = getDesksCount();
            const desks = [];
            
            for (let i = 1; i <= total; i++) {
                const desk = document.getElementById(`desk-${i}`);
                if (desk) desks.push(desk);
            }
            
            if (desks.length === total && total > 0) {
                console.log(`✅ Все ${total} столов готовы`);
                resolve();
            } else if (Date.now() - startTime > timeout) {
                console.warn(`⏱️ Таймаут: найдено ${desks.length} из ${total} столов`);
                resolve();  // Продолжаем даже если не все найдены
            } else {
                setTimeout(check, 100);
            }
        };
        
        check();
    });
}

// 🆕 Обновлённая updateStatus для динамических столов
async function updateStatus() {
    const totalDesks = getDesksCount();
    
    // Проверка готовности
    const firstDesk = document.getElementById('desk-1');
    if (!firstDesk && totalDesks > 0) {
        console.warn('⚠️ Столы ещё не в DOM, пропускаем обновление');
        return;
    }
    
    try {
        const response = await fetch('/api/status', {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            cache: 'no-store'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log(`✅ Получены данные: ${data.present_count}/${data.total_desks} сотрудников`);
        
        // 🆕 Обновление динамических столов
        if (Array.isArray(data.desks)) {
            data.desks.forEach(desk => {
                const element = document.getElementById(`desk-${desk.id}`);
                if (element) {
                    const wasPresent = element.classList.contains('present');
                    const isPresent = desk.is_present;
                    
                    // Обновляем классы
                    element.classList.toggle('present', isPresent);
                    element.classList.toggle('absent', !isPresent);
                    
                    // Обновляем текст
                    const statusEl = element.querySelector('.desk-status');
                    if (statusEl) {
                        statusEl.textContent = isPresent ? '✓ В офисе' : '○ Нет на месте';
                    }
                    
                    // Анимация при изменении
                    if (wasPresent !== isPresent) {
                        element.style.transition = 'transform 0.3s ease';
                        element.style.transform = 'scale(1.02)';
                        setTimeout(() => {
                            element.style.transform = '';
                        }, 300);
                    }
                } else {
                    console.warn(`⚠️ Стол #${desk.id} не найден в DOM`);
                }
            });
        }
        
        // Обновление статистики
        updateStats(data);
        
        // Уведомления
        if (typeof checkNotificationEvents === 'function') {
            await checkNotificationEvents();
        }
        
    } catch (error) {
        console.error('❌ Ошибка обновления:', error);
        showTemporaryError('Не удалось обновить статус');
    }
}

function updateStats(data) {
    // 🆕 Обновляем количество присутствующих (только число)
    const presentEl = document.getElementById('present-count');
    if (presentEl && data.present_count !== undefined) {
        presentEl.textContent = data.present_count;
    }
    
    // 🆕 Обновляем общее количество столов
    const totalEl = document.getElementById('total-desks');
    if (totalEl) {
        const total = data.total_desks || getDesksCount();
        totalEl.textContent = total;
    }
    
    // Гости
    const guestsEl = document.getElementById('guests-section') || 
                     document.querySelector('.guests-count');
    if (guestsEl && data.guests_count !== undefined) {
        if (data.guests_count > 0) {
            guestsEl.textContent = `| Гости: ${data.guests_count}`;
            guestsEl.style.display = 'inline';
        } else {
            guestsEl.style.display = 'none';
        }
    }
    
    // Последний визит
    const lastVisitEl = document.getElementById('last-visit-section') ||
                        document.querySelector('.last-visit');
    if (lastVisitEl && data.is_empty !== undefined) {
        if (data.is_empty) {
            lastVisitEl.style.display = 'block';
            if (data.last_visit) {
                const strong = lastVisitEl.querySelector('strong');
                if (strong) strong.textContent = data.last_visit;
            }
        } else {
            lastVisitEl.style.display = 'none';
        }
    }
}

// Инициализация
document.addEventListener('DOMContentLoaded', async () => {
    console.log('📄 DOM загружен, столов:', getDesksCount());
    
    updateTime();
    setInterval(updateTime, 1000);
    
    if (typeof initNotifications === 'function') {
        initNotifications();
    }
    
    // Ждём готовности столов
    await new Promise(resolve => setTimeout(resolve, 500));
    await waitForDesks();
    
    pageReady = true;
    await updateStatus();
    
    // Автообновление
    setInterval(() => {
        if (pageReady) updateStatus();
    }, 30000);
    
    // Кнопка обновить
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', (e) => {
            e.preventDefault();
            updateStatus();
        });
    }
    
    console.log('✅ Инициализация завершена');
});