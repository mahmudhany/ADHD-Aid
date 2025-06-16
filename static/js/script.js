document.addEventListener('DOMContentLoaded', function() {
    const statusText = document.getElementById('status-text');
    const statusIcon = document.getElementById('status-icon');
    const startSessionBtn = document.getElementById('startSessionBtn');
    const endSessionBtn = document.getElementById('endSessionBtn');
    const focusTimeElement = document.getElementById('focus-time');
    const unfocusTimeElement = document.getElementById('unfocus-time');
    const focusPercentageElement = document.getElementById('focus-percentage');
    const historyContainer = document.getElementById('history-container');
    const progressChart = document.getElementById('progress-chart');
    
    let updateInterval;
    let lastDirection = '';
    
    function updateEyeState() {
        fetch('/get_eye_state')
            .then(response => response.json())
            .then(data => {
                updateUI(data);
            })
            .catch(error => {
                console.error('Error:', error);
            });
    }
    
    function updateStats() {
        fetch('/get_stats')
            .then(response => response.json())
            .then(data => {
                updateStatsUI(data);
            })
            .catch(error => {
                console.error('Error:', error);
            });
    }
    
    function updateUI(data) {
        const statusElement = document.querySelector('.status');
        
        if (data.direction !== lastDirection) {
            let directionText = '';
            let icon = '👁️';
            
            switch(data.direction) {
                case 'CENTER':
                    directionText = 'تركيز جيد';
                    icon = '👌';
                    break;
                case 'LEFT':
                    directionText = 'ينظر لليسار';
                    icon = '👈';
                    break;
                case 'RIGHT':
                    directionText = 'ينظر لليمين';
                    icon = '👉';
                    break;
                default:
                    directionText = 'جاري التتبع...';
            }
            
            statusText.textContent = directionText;
            statusIcon.textContent = icon;
            lastDirection = data.direction;
            
            statusElement.classList.remove('center', 'left', 'right', 'warning');
            statusElement.classList.add(data.direction.toLowerCase());
            
            if (data.warned) {
                statusElement.classList.add('warning');
            }
        }
    }
    
    function updateStatsUI(data) {
        focusTimeElement.textContent = formatDuration(data.total_focus || 0);
        unfocusTimeElement.textContent = formatDuration(data.total_unfocus || 0);
        focusPercentageElement.textContent = data.focus_percentage ? data.focus_percentage.toFixed(1) + '%' : '0%';
    }
    
    function loadHistory() {
        fetch('/get_history')
            .then(response => response.json())
            .then(data => {
                renderHistory(data);
                renderProgressChart(data);
            });
    }
    
    function renderHistory(history) {
        if (!historyContainer) return;
        
        historyContainer.innerHTML = history.map(session => `
            <div class="history-session">
                <div class="session-header">
                    <h4>جلسة ${session.date} ${session.start_time}</h4>
                    <span class="percentage ${getPercentageClass(session.focus_percentage)}">
                        ${session.focus_percentage.toFixed(1)}%
                    </span>
                </div>
                <div class="session-details">
                    <div class="session-stats">
                        <span>تركيز: ${formatDuration(session.total_focus)}</span>
                        <span>عدم تركيز: ${formatDuration(session.total_unfocus)}</span>
                    </div>
                    <div class="session-periods">
                        ${session.periods.map(p => `
                            <div class="period ${p.type}" 
                                 style="width: ${(p.duration / (session.total_focus + session.total_unfocus)) * 100}%"
                                 title="${p.type === 'focus' ? 'تركيز' : 'عدم تركيز'}: ${formatDuration(p.duration)}">
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `).join('');
    }
    
    function renderProgressChart(history) {
        if (!progressChart || history.length < 2) return;
        
        const dates = history.map(s => s.date).reverse();
        const percentages = history.map(s => s.focus_percentage).reverse();
        
        progressChart.innerHTML = `
            <div class="chart">
                <div class="chart-labels">
                    ${dates.map((d, i) => `
                        <div class="chart-label">
                            <span>${d}</span>
                            <span class="chart-value">${percentages[i].toFixed(1)}%</span>
                        </div>
                    `).join('')}
                </div>
                <div class="chart-bars">
                    ${percentages.map(p => `
                        <div class="chart-bar-container">
                            <div class="chart-bar" style="height: ${p}%"></div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    function formatDuration(seconds) {
        seconds = Math.floor(seconds);
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins} دقيقة ${secs} ثانية`;
    }
    
    function getPercentageClass(percentage) {
        if (percentage >= 70) return "high";
        if (percentage >= 40) return "medium";
        return "low";
    }
    
    startSessionBtn.addEventListener('click', function() {
        fetch('/start_session')
            .then(response => response.json())
            .then(data => {
                if (!updateInterval) {
                    updateInterval = setInterval(() => {
                        updateEyeState();
                        updateStats();
                    }, 500);
                }
                startSessionBtn.disabled = true;
                endSessionBtn.disabled = false;
                loadHistory();
            })
            .catch(error => {
                console.error('Error:', error);
            });
    });
    
    endSessionBtn.addEventListener('click', function() {
        fetch('/end_session')
            .then(response => response.json())
            .then(data => {
                if (updateInterval) {
                    clearInterval(updateInterval);
                    updateInterval = null;
                }
                statusText.textContent = 'جاهز للبدء';
                statusIcon.textContent = '👁️';
                document.querySelector('.status').className = 'status';
                startSessionBtn.disabled = false;
                endSessionBtn.disabled = true;
                loadHistory();
            })
            .catch(error => {
                console.error('Error:', error);
            });
    });
    
    endSessionBtn.disabled = true;
    
    loadHistory();
});