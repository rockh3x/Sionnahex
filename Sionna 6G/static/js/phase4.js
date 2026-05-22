/**
 * Sionnah3x — Phase 4 Features
 * Dashboard analytics, notification center, parameter validation,
 * simulation queue, compare lab, responsive layout, search
 */

// ═══════════════════════════════════════════════════════════════════════════
//  Notification Center
// ═══════════════════════════════════════════════════════════════════════════

const NotificationCenter = {
    _events: [],
    _unread: 0,
    _maxEvents: 50,

    init() {
        // Load from sessionStorage (session-scoped, not persisted across tabs)
        const saved = sessionStorage.getItem('sionna_notifications');
        if (saved) {
            try {
                this._events = JSON.parse(saved);
                this._unread = this._events.filter(e => !e.read).length;
            } catch (e) { /* ignore */ }
        }
        this._updateBadge();
    },

    add(message, type = 'info', icon = 'ℹ️') {
        const event = {
            id: Date.now(),
            message,
            type,
            icon,
            read: false,
            time: new Date().toLocaleTimeString()
        };
        this._events.unshift(event);
        if (this._events.length > this._maxEvents) this._events.pop();
        this._unread++;
        this._save();
        this._updateBadge();
        this._renderFeed();
    },

    markAllRead() {
        this._events.forEach(e => e.read = true);
        this._unread = 0;
        this._save();
        this._updateBadge();
        this._renderFeed();
    },

    clear() {
        this._events = [];
        this._unread = 0;
        this._save();
        this._updateBadge();
        this._renderFeed();
    },

    _save() {
        sessionStorage.setItem('sionna_notifications', JSON.stringify(this._events));
    },

    _updateBadge() {
        const badge = document.getElementById('notif-badge');
        if (badge) {
            badge.textContent = this._unread;
            badge.style.display = this._unread > 0 ? 'flex' : 'none';
        }
    },

    _renderFeed() {
        const list = document.getElementById('notif-list');
        if (!list) return;
        if (this._events.length === 0) {
            list.innerHTML = '<div class="notif-empty">No notifications yet</div>';
            return;
        }
        list.innerHTML = this._events.slice(0, 20).map(e => `
            <div class="notif-item ${e.read ? '' : 'unread'}" data-type="${e.type}">
                <span class="notif-icon">${e.icon}</span>
                <div class="notif-content">
                    <div class="notif-msg">${e.message}</div>
                    <div class="notif-time">${e.time}</div>
                </div>
            </div>
        `).join('');
    },

    toggle() {
        const panel = document.getElementById('notif-panel');
        if (!panel) return;
        const isOpen = panel.style.display === 'block';
        panel.style.display = isOpen ? 'none' : 'block';
        if (!isOpen) {
            this.markAllRead();
            this._renderFeed();
        }
    }
};

// Override showToast to also feed the notification center
const _origShowToast = typeof showToast === 'function' ? showToast : null;
function showToastWithNotif(message, type = 'info') {
    // Call original toast
    if (_origShowToast) _origShowToast(message, type);
    // Add to notification center
    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    NotificationCenter.add(message, type, icons[type] || 'ℹ️');
}
// We'll override showToast at DOMContentLoaded


// ═══════════════════════════════════════════════════════════════════════════
//  Dashboard Analytics
// ═══════════════════════════════════════════════════════════════════════════

let distributionChart = null;
let activityChart = null;

async function loadAnalytics() {
    try {
        const res = await API.get('/api/analytics');
        if (res.status !== 'success') return;
        const data = res.data;
        renderDistributionChart(data.distribution);
        renderActivityChart(data.daily_activity);
        renderBerTrend(data.ber_trends);
        renderModUsage(data.modulation_usage);
    } catch (e) { /* silent */ }
}

function renderDistributionChart(distribution) {
    const canvas = document.getElementById('analytics-distribution');
    if (!canvas || !distribution) return;

    const labels = Object.keys(distribution).map(k => k.toUpperCase());
    const values = Object.values(distribution);
    const colors = ['#76B900', '#00d4ff', '#ff6b35', '#a855f7', '#ec4899'];

    if (distributionChart) distributionChart.destroy();
    distributionChart = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors.slice(0, values.length),
                borderWidth: 0,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#9999bb', font: { family: 'Inter', size: 11 }, padding: 12 }
                }
            }
        }
    });
}

function renderActivityChart(dailyActivity) {
    const canvas = document.getElementById('analytics-activity');
    if (!canvas) return;

    // Fill in missing days
    const days = [];
    const counts = [];
    const actMap = {};
    dailyActivity.forEach(d => actMap[d.day] = d.count);

    for (let i = 13; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        const key = date.toISOString().split('T')[0];
        const label = date.toLocaleDateString('en', { month: 'short', day: 'numeric' });
        days.push(label);
        counts.push(actMap[key] || 0);
    }

    if (activityChart) activityChart.destroy();
    activityChart = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: days,
            datasets: [{
                label: 'Simulations',
                data: counts,
                backgroundColor: 'rgba(118, 185, 0, 0.5)',
                borderColor: '#76B900',
                borderWidth: 1,
                borderRadius: 4,
                barPercentage: 0.6
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { ticks: { color: '#666', font: { size: 9 } }, grid: { display: false } },
                y: { beginAtZero: true, ticks: { color: '#666', stepSize: 1, font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.04)' } }
            }
        }
    });
}

function renderBerTrend(berTrends) {
    const container = document.getElementById('analytics-ber-trend');
    if (!container || !berTrends || berTrends.length === 0) {
        if (container) container.innerHTML = '<div class="analytics-empty">No BER simulations yet</div>';
        return;
    }
    container.innerHTML = berTrends.slice(0, 6).map(t => `
        <div class="ber-trend-item">
            <span class="trend-name" title="${t.name}">${t.name}</span>
            <span class="trend-ber">${t.min_ber > 0 ? t.min_ber.toExponential(1) : '0'}</span>
        </div>
    `).join('');
}

function renderModUsage(modUsage) {
    const container = document.getElementById('analytics-mod-usage');
    if (!container || !modUsage) return;
    const total = Object.values(modUsage).reduce((a, b) => a + b, 0);
    if (total === 0) { container.innerHTML = '<div class="analytics-empty">No data</div>'; return; }
    container.innerHTML = Object.entries(modUsage)
        .sort((a, b) => b[1] - a[1])
        .map(([mod, count]) => {
            const pct = Math.round(count / total * 100);
            return `<div class="mod-usage-item">
                <span class="mod-name">${mod.toUpperCase()}</span>
                <div class="mod-bar-track"><div class="mod-bar-fill" style="width:${pct}%"></div></div>
                <span class="mod-count">${count}</span>
            </div>`;
        }).join('');
}


// ═══════════════════════════════════════════════════════════════════════════
//  Parameter Validation & Smart Defaults
// ═══════════════════════════════════════════════════════════════════════════

function initParameterValidation() {
    const inputs = ['ber-snr-min', 'ber-snr-max', 'ber-snr-step', 'ber-num-bits', 'ber-modulation'];
    inputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', validateBerParams);
    });
    // Initial validation
    setTimeout(validateBerParams, 500);
}

function validateBerParams() {
    const container = document.getElementById('ber-validation-msg');
    if (!container) return;

    const snrMin = parseFloat(document.getElementById('ber-snr-min')?.value || 0);
    const snrMax = parseFloat(document.getElementById('ber-snr-max')?.value || 20);
    const snrStep = parseFloat(document.getElementById('ber-snr-step')?.value || 2);
    const numBits = parseInt(document.getElementById('ber-num-bits')?.value || 100000);
    const mod = document.getElementById('ber-modulation')?.value || 'qpsk';
    const minErrors = parseInt(document.getElementById('ber-min-errors')?.value || 100);
    const maxIter = parseInt(document.getElementById('ber-max-iter')?.value || 50);

    const messages = [];

    // SNR range validation
    if (snrMin >= snrMax) {
        messages.push({ type: 'error', text: 'SNR Min must be less than SNR Max' });
    }
    if (snrStep <= 0) {
        messages.push({ type: 'error', text: 'SNR step must be positive' });
    }
    if (snrStep > (snrMax - snrMin)) {
        messages.push({ type: 'warn', text: 'Step size is larger than SNR range — only 1 point will be simulated' });
    }

    // Modulation hints
    const modHints = {
        '256qam': { minSnr: 20, tip: '256-QAM typically needs SNR > 20 dB for meaningful BER' },
        '64qam': { minSnr: 15, tip: '64-QAM works best with SNR range starting above 10 dB' },
        '16qam': { minSnr: 8, tip: '16-QAM: consider SNR range 5–25 dB for full waterfall' }
    };
    if (modHints[mod] && snrMax < modHints[mod].minSnr) {
        messages.push({ type: 'info', text: modHints[mod].tip });
    }

    // Estimate simulation time
    const numPoints = Math.ceil((snrMax - snrMin) / snrStep) + 1;
    const estTimePerPoint = (numBits * maxIter / 1e6) * 0.05; // rough ms per point
    const estTime = numPoints * estTimePerPoint;

    // Update estimate badge
    const estEl = document.getElementById('ber-time-estimate');
    if (estEl) {
        if (estTime < 1) estEl.textContent = `~${Math.round(estTime * 1000)}ms`;
        else if (estTime < 60) estEl.textContent = `~${Math.round(estTime)}s`;
        else estEl.textContent = `~${(estTime / 60).toFixed(1)}min`;
    }

    // Render messages
    if (messages.length === 0) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = messages.map(m =>
        `<div class="validation-msg ${m.type}">${m.type === 'error' ? '❌' : m.type === 'warn' ? '⚠️' : '💡'} ${m.text}</div>`
    ).join('');
}


// ═══════════════════════════════════════════════════════════════════════════
//  Simulation Queue
// ═══════════════════════════════════════════════════════════════════════════

const SimQueue = {
    _queue: [],
    _running: false,

    init() {
        const saved = localStorage.getItem('sim_queue');
        if (saved) {
            try { this._queue = JSON.parse(saved); } catch (e) { this._queue = []; }
        }
        this._render();
    },

    add() {
        const params = {
            modulation: document.getElementById('ber-modulation')?.value || 'qpsk',
            channel: document.getElementById('ber-channel')?.value || 'awgn',
            coding: document.getElementById('ber-coding')?.value || 'uncoded',
            snr_min: document.getElementById('ber-snr-min')?.value || '0',
            snr_max: document.getElementById('ber-snr-max')?.value || '20',
            snr_step: document.getElementById('ber-snr-step')?.value || '2',
            num_bits: document.getElementById('ber-num-bits')?.value || '100000',
            min_errors: document.getElementById('ber-min-errors')?.value || '100',
            max_iterations: document.getElementById('ber-max-iter')?.value || '50',
            seed: document.getElementById('ber-seed')?.value || 'auto',
            num_tx: document.getElementById('ber-num-tx')?.value || '1',
            num_rx: document.getElementById('ber-num-rx')?.value || '1'
        };
        const label = `${params.modulation.toUpperCase()}/${params.channel.toUpperCase()}/${params.coding.toUpperCase()}`;
        this._queue.push({ id: Date.now(), label, params, status: 'pending' });
        this._save();
        this._render();
        showToast(`Added "${label}" to queue`, 'success');
    },

    remove(id) {
        this._queue = this._queue.filter(q => q.id !== id);
        this._save();
        this._render();
    },

    clearCompleted() {
        this._queue = this._queue.filter(q => q.status !== 'completed' && q.status !== 'error');
        this._save();
        this._render();
    },

    async runAll() {
        if (this._running) return;
        const pending = this._queue.filter(q => q.status === 'pending');
        if (pending.length === 0) return showToast('No pending simulations in queue', 'info');

        this._running = true;
        const btn = document.getElementById('btn-run-queue');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Running...'; }

        for (const item of pending) {
            item.status = 'running';
            this._save();
            this._render();

            try {
                const res = await API.post('/api/simulate/ber', item.params);
                if (res.status === 'success') {
                    item.status = 'completed';
                    item.sim_id = res.data.sim_id;
                    showToast(`Queue: "${item.label}" completed`, 'success');
                } else {
                    item.status = 'error';
                    showToast(`Queue: "${item.label}" failed`, 'error');
                }
            } catch (e) {
                item.status = 'error';
                showToast(`Queue: "${item.label}" error: ${e.message}`, 'error');
            }
            this._save();
            this._render();
        }

        this._running = false;
        if (btn) { btn.disabled = false; btn.textContent = '▶ Run Queue'; }
        showToast(`Queue finished: ${pending.length} simulations`, 'success');
    },

    _save() {
        localStorage.setItem('sim_queue', JSON.stringify(this._queue));
    },

    _render() {
        const container = document.getElementById('queue-list');
        const badge = document.getElementById('queue-count');
        const pending = this._queue.filter(q => q.status === 'pending').length;
        if (badge) {
            badge.textContent = this._queue.length;
            badge.style.display = this._queue.length > 0 ? 'inline' : 'none';
        }
        if (!container) return;
        if (this._queue.length === 0) {
            container.innerHTML = '<div class="queue-empty">Queue is empty. Add simulations with the + button.</div>';
            return;
        }
        container.innerHTML = this._queue.map(q => {
            const statusIcons = { pending: '⏳', running: '🔄', completed: '✅', error: '❌' };
            return `<div class="queue-item ${q.status}">
                <span class="queue-status">${statusIcons[q.status] || '⏳'}</span>
                <span class="queue-label">${q.label}</span>
                <span class="queue-snr">${q.params.snr_min}–${q.params.snr_max} dB</span>
                ${q.status === 'pending' ? `<button class="btn btn-secondary btn-sm queue-remove" onclick="SimQueue.remove(${q.id})" title="Remove">✕</button>` : ''}
            </div>`;
        }).join('');
    }
};


// ═══════════════════════════════════════════════════════════════════════════
//  Compare Lab
// ═══════════════════════════════════════════════════════════════════════════

let compareChart = null;
let compareSelections = [];

async function loadCompareSimulations() {
    const listContainer = document.getElementById('compare-sim-list');
    if (!listContainer) return;
    try {
        const res = await API.get('/api/history?type=ber&limit=30');
        if (res.status !== 'success' || !res.data.length) {
            listContainer.innerHTML = '<div class="analytics-empty">No BER simulations available for comparison</div>';
            return;
        }
        listContainer.innerHTML = res.data.map(sim => {
            const meta = sim.results?.metadata || {};
            const isSelected = compareSelections.includes(sim.id);
            return `<div class="compare-sim-row ${isSelected ? 'selected' : ''}" onclick="toggleCompareSelection(${sim.id})">
                <input type="checkbox" ${isSelected ? 'checked' : ''} class="compare-cb" />
                <span class="compare-name">#${sim.id} ${sim.name || 'Unnamed'}</span>
                <span class="compare-meta">${(meta.modulation || '').toUpperCase()} / ${(meta.channel || '').toUpperCase()}</span>
            </div>`;
        }).join('');
    } catch (e) {
        listContainer.innerHTML = '<div class="analytics-empty">Failed to load simulations</div>';
    }
}

function toggleCompareSelection(simId) {
    const idx = compareSelections.indexOf(simId);
    if (idx >= 0) {
        compareSelections.splice(idx, 1);
    } else {
        if (compareSelections.length >= 6) return showToast('Max 6 simulations for comparison', 'error');
        compareSelections.push(simId);
    }
    loadCompareSimulations();
}

async function runComparison() {
    if (compareSelections.length < 2) return showToast('Select at least 2 simulations', 'error');
    const resultsDiv = document.getElementById('compare-results');
    if (!resultsDiv) return;
    resultsDiv.innerHTML = '<div class="empty-state" style="padding:30px"><div class="spinner"></div></div>';

    try {
        const sims = [];
        for (const id of compareSelections) {
            const res = await API.get(`/api/history/${id}`);
            if (res.status === 'success') sims.push(res.data);
        }
        if (sims.length < 2) return showToast('Could not load simulations', 'error');
        renderComparisonResults(sims);
    } catch (e) {
        resultsDiv.innerHTML = '<div class="analytics-empty">Failed to load</div>';
    }
}

function renderComparisonResults(sims) {
    const resultsDiv = document.getElementById('compare-results');
    const colors = ['#76B900', '#00d4ff', '#ff6b35', '#a855f7', '#ec4899', '#f59e0b'];

    // Chart
    resultsDiv.innerHTML = `
        <div class="section-title">📊 BER Comparison</div>
        <div class="plot-container"><canvas id="compare-chart" height="350"></canvas></div>
        <div class="section-title" style="margin-top:20px">📋 Parameter Diff</div>
        <div id="compare-diff-table"></div>
    `;

    const ctx = document.getElementById('compare-chart').getContext('2d');
    if (compareChart) compareChart.destroy();

    const datasets = [];
    sims.forEach((sim, i) => {
        const r = sim.results || {};
        const meta = r.metadata || {};
        const label = `#${sim.id} ${(meta.modulation || '').toUpperCase()}/${(meta.channel || '').toUpperCase()}`;
        datasets.push({
            label: `${label} (Sim)`, data: r.ber_values || [],
            borderColor: colors[i % colors.length], borderWidth: 2.5,
            pointRadius: 4, pointBackgroundColor: colors[i % colors.length],
            fill: false, tension: 0.1
        });
        if (r.theoretical_ber) {
            datasets.push({
                label: `${label} (Theo)`, data: r.theoretical_ber,
                borderColor: colors[i % colors.length], borderWidth: 1.5,
                borderDash: [6, 3], pointRadius: 0, fill: false, tension: 0.3
            });
        }
    });

    const labels = (sims[0].results?.snr_values || []).map(v => `${v}`);
    compareChart = new Chart(ctx, {
        type: 'line', data: { labels, datasets },
        options: {
            responsive: true, interaction: { mode: 'index', intersect: false },
            plugins: { legend: { labels: { color: '#aaa', font: { family: 'Inter', size: 10 } } } },
            scales: {
                x: { title: { display: true, text: 'Eb/N0 (dB)', color: '#888' }, ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { type: 'logarithmic', title: { display: true, text: 'BER', color: '#888' }, ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' }, min: 1e-7 }
            }
        }
    });

    // Diff table
    const diffContainer = document.getElementById('compare-diff-table');
    const allParams = new Set();
    sims.forEach(sim => Object.keys(sim.parameters || {}).forEach(k => allParams.add(k)));

    let diffHTML = '<table class="history-table"><thead><tr><th>Parameter</th>';
    sims.forEach((sim, i) => diffHTML += `<th style="color:${colors[i % colors.length]}">#${sim.id}</th>`);
    diffHTML += '</tr></thead><tbody>';

    for (const param of allParams) {
        const values = sims.map(s => (s.parameters || {})[param] ?? '—');
        const allSame = values.every(v => v === values[0]);
        diffHTML += `<tr${!allSame ? ' class="diff-highlight"' : ''}>`;
        diffHTML += `<td><strong>${param}</strong></td>`;
        values.forEach(v => diffHTML += `<td>${v}</td>`);
        diffHTML += '</tr>';
    }
    diffHTML += '</tbody></table>';
    diffContainer.innerHTML = diffHTML;
}


// ═══════════════════════════════════════════════════════════════════════════
//  History Search
// ═══════════════════════════════════════════════════════════════════════════

let _searchTimer = null;
function searchHistory(query) {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => {
        loadHistory(query);
    }, 300);
}


// ═══════════════════════════════════════════════════════════════════════════
//  Report Generator
// ═══════════════════════════════════════════════════════════════════════════

let reportSelections = new Set();

function toggleReportSelection(simId, checkbox) {
    if (checkbox.checked) {
        reportSelections.add(simId);
    } else {
        reportSelections.delete(simId);
    }
    const countEl = document.getElementById('report-count');
    if (countEl) countEl.textContent = reportSelections.size;
}

async function generateReport() {
    if (reportSelections.size === 0) return showToast('Select simulations for the report', 'error');
    try {
        const res = await fetch('/api/export/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sim_ids: Array.from(reportSelections),
                title: `Sionnah3x Research Report — ${new Date().toLocaleDateString()}`
            })
        });
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `research_report_${Date.now()}.html`;
        a.click();
        URL.revokeObjectURL(url);
        showToast(`Report generated with ${reportSelections.size} simulations`, 'success');
    } catch (e) {
        showToast(`Report failed: ${e.message}`, 'error');
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Responsive Sidebar Toggle
// ═══════════════════════════════════════════════════════════════════════════

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (sidebar) sidebar.classList.toggle('open');
    if (backdrop) backdrop.classList.toggle('active');
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (sidebar) sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('active');
}


// ═══════════════════════════════════════════════════════════════════════════
//  Initialize Phase 4
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    NotificationCenter.init();
    SimQueue.init();
    initParameterValidation();

    // Override showToast globally after load
    if (typeof window.showToast === 'function') {
        const origToast = window.showToast;
        window.showToast = function(message, type) {
            origToast(message, type);
            const icons = { success: '✅', error: '❌', info: 'ℹ️' };
            NotificationCenter.add(message, type, icons[type] || 'ℹ️');
        };
    }

    // Close sidebar on nav click (mobile)
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            if (window.innerWidth < 1024) closeSidebar();
        });
    });

    // Close notification panel on outside click
    document.addEventListener('click', (e) => {
        const panel = document.getElementById('notif-panel');
        const bell = document.getElementById('notif-bell');
        if (panel && panel.style.display === 'block' && !panel.contains(e.target) && !bell?.contains(e.target)) {
            panel.style.display = 'none';
        }
    });
});
