/**
 * Sionnah3x — Phase 5 Features
 * SSE streaming BER, favorites, detail modal,
 * session stats, preset cards, keyboard shortcut help
 */

// ═══════════════════════════════════════════════════════════════════════════
//  Session Stats Tracker
// ═══════════════════════════════════════════════════════════════════════════

const SessionStats = {
    _simCount: 0,
    _totalTimeMs: 0,

    increment(elapsedSec) {
        this._simCount++;
        this._totalTimeMs += (elapsedSec || 0) * 1000;
        this._update();
    },

    _update() {
        const countEl = document.getElementById('ss-sim-count');
        const timeEl = document.getElementById('ss-total-time');
        const queueEl = document.getElementById('ss-queue-depth');

        if (countEl) countEl.textContent = this._simCount;
        if (timeEl) {
            const sec = Math.round(this._totalTimeMs / 1000);
            timeEl.textContent = sec < 60 ? `${sec}s` : `${(sec / 60).toFixed(1)}m`;
        }
        if (queueEl && typeof SimQueue !== 'undefined') {
            const pending = SimQueue._queue ? SimQueue._queue.filter(q => q.status === 'pending').length : 0;
            queueEl.textContent = pending;
        }
    },

    updateFavorites(count) {
        const el = document.getElementById('ss-favorites');
        if (el) el.textContent = count;
    }
};


// ═══════════════════════════════════════════════════════════════════════════
//  Favorites / Pinning
// ═══════════════════════════════════════════════════════════════════════════

async function toggleFavorite(simId, event) {
    if (event) event.stopPropagation();
    try {
        const res = await fetch(`/api/history/${simId}/favorite`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(data.is_favorite ? '⭐ Added to favorites' : 'Removed from favorites', 'info');
            loadHistory();
            loadFavoritesCount();
        }
    } catch (e) {
        showToast('Failed to toggle favorite', 'error');
    }
}

async function loadFavoritesCount() {
    try {
        const res = await API.get('/api/history?limit=200');
        if (res.status === 'success') {
            const favCount = res.data.filter(s => s.is_favorite).length;
            SessionStats.updateFavorites(favCount);
        }
    } catch (e) { /* silent */ }
}


// ═══════════════════════════════════════════════════════════════════════════
//  History Detail Modal
// ═══════════════════════════════════════════════════════════════════════════

async function showHistoryDetail(simId) {
    const modal = document.getElementById('history-detail-modal');
    const titleEl = document.getElementById('history-detail-title');
    const bodyEl = document.getElementById('history-detail-body');
    if (!modal || !bodyEl) return;

    modal.style.display = 'flex';
    bodyEl.innerHTML = '<div class="empty-state" style="padding:40px"><div class="spinner"></div></div>';

    try {
        const res = await API.get(`/api/history/${simId}`);
        if (res.status !== 'success') {
            bodyEl.innerHTML = '<div class="empty-state"><div class="empty-state-title">Not Found</div></div>';
            return;
        }
        const sim = res.data;
        const params = sim.parameters || {};
        const results = sim.results || {};
        const meta = results.metadata || {};
        const st = sim.sim_type;

        titleEl.textContent = `#${sim.id} — ${sim.name || 'Unnamed'}`;

        let html = `
            <div class="detail-badges">
                <span class="history-type-badge badge-${st}">${st}</span>
                ${sim.is_favorite ? '<span class="fav-badge">⭐ Favorite</span>' : ''}
                <span class="detail-date">${new Date(sim.created_at).toLocaleString()}</span>
            </div>

            <div class="section-title" style="margin-top:16px;">🎛️ Parameters</div>
            <div class="params-grid">
                ${Object.entries(params).map(([k, v]) => `
                    <div class="param-detail-item">
                        <span class="param-key">${k}</span>
                        <span class="param-val">${v}</span>
                    </div>
                `).join('')}
            </div>
        `;

        // BER chart in modal
        if (st === 'ber' && results.snr_values) {
            html += `
                <div class="section-title" style="margin-top:20px;">📊 BER Curve</div>
                <div class="plot-container"><canvas id="detail-ber-chart" height="250"></canvas></div>
                <div class="metrics-grid">
                    <div class="metric-item"><div class="metric-value">${meta.modulation?.toUpperCase() || '—'}</div><div class="metric-label">Modulation</div></div>
                    <div class="metric-item"><div class="metric-value">${meta.channel?.toUpperCase() || '—'}</div><div class="metric-label">Channel</div></div>
                    <div class="metric-item"><div class="metric-value">${meta.coding?.toUpperCase() || '—'}</div><div class="metric-label">Coding</div></div>
                    <div class="metric-item"><div class="metric-value">${meta.elapsed_seconds || '—'}s</div><div class="metric-label">Runtime</div></div>
                    <div class="metric-item"><div class="metric-value">${meta.seed || '—'}</div><div class="metric-label">Seed</div></div>
                    <div class="metric-item"><div class="metric-value">${meta.engine || '—'}</div><div class="metric-label">Engine</div></div>
                </div>
            `;
        }

        // Constellation plot
        if (st === 'constellation' && results.plot) {
            html += `
                <div class="section-title" style="margin-top:20px;">🔵 Constellation</div>
                <div class="plot-container"><img src="data:image/png;base64,${results.plot}" alt="Constellation" /></div>
            `;
        }

        // Channel plots
        if (st === 'channel' && results.cir_plot) {
            html += `
                <div class="section-title" style="margin-top:20px;">📡 Channel Impulse Response</div>
                <div class="plot-container"><img src="data:image/png;base64,${results.cir_plot}" alt="CIR" /></div>
            `;
        }

        // OFDM plots
        if (st === 'ofdm' && results.spectrum_plot) {
            html += `
                <div class="section-title" style="margin-top:20px;">📶 OFDM Spectrum</div>
                <div class="plot-container"><img src="data:image/png;base64,${results.spectrum_plot}" alt="Spectrum" /></div>
            `;
        }

        // Notes
        html += `
            <div class="section-title" style="margin-top:20px;">📝 Research Notes</div>
            <textarea class="notes-textarea" id="detail-notes" placeholder="Add research notes..."
                oninput="saveNotes(${sim.id}, this.value, '')">${sim.notes || ''}</textarea>
        `;

        // Export buttons
        html += `
            <div class="detail-actions">
                <button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/${sim.id}/csv')">📄 CSV</button>
                <button class="btn btn-secondary btn-sm" onclick="exportSimulation(${sim.id})">📋 JSON</button>
                ${st === 'ber' ? `<button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/${sim.id}/latex')">📝 LaTeX</button>` : ''}
                <button class="btn btn-secondary btn-sm" onclick="toggleFavorite(${sim.id})">${sim.is_favorite ? '★ Unfavorite' : '☆ Favorite'}</button>
            </div>
        `;

        bodyEl.innerHTML = html;

        // Render BER chart in modal
        if (st === 'ber' && results.snr_values) {
            setTimeout(() => {
                const ctx = document.getElementById('detail-ber-chart');
                if (!ctx) return;
                const datasets = [{
                    label: 'BER (Simulated)', data: results.ber_values,
                    borderColor: '#76B900', backgroundColor: 'rgba(118,185,0,0.1)',
                    borderWidth: 2.5, pointRadius: 4, pointBackgroundColor: '#76B900',
                    fill: false, tension: 0.1
                }];
                if (results.theoretical_ber) {
                    datasets.push({
                        label: 'BER (Theoretical)', data: results.theoretical_ber,
                        borderColor: '#ff6b35', borderWidth: 2, pointRadius: 0,
                        borderDash: [8, 4], fill: false, tension: 0.3
                    });
                }
                new Chart(ctx.getContext('2d'), {
                    type: 'line',
                    data: { labels: results.snr_values.map(v => `${v}`), datasets },
                    options: {
                        responsive: true,
                        plugins: { legend: { labels: { color: '#aaa', font: { family: 'Inter', size: 11 } } } },
                        scales: {
                            x: { title: { display: true, text: 'Eb/N0 (dB)', color: '#888' }, ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' } },
                            y: { type: 'logarithmic', title: { display: true, text: 'BER', color: '#888' }, ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' }, min: 1e-7 }
                        }
                    }
                });
            }, 100);
        }

    } catch (e) {
        bodyEl.innerHTML = `<div class="empty-state"><div class="empty-state-title">Error loading simulation</div></div>`;
    }
}

function closeHistoryDetail(event) {
    if (event.target.id === 'history-detail-modal') {
        document.getElementById('history-detail-modal').style.display = 'none';
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Enhanced History with Favorites Star
// ═══════════════════════════════════════════════════════════════════════════

// Override loadHistory to include favorite stars
const _origLoadHistory = typeof loadHistory === 'function' ? loadHistory : null;

window.loadHistory = async function(searchQuery) {
    const filter = document.getElementById('history-filter')?.value || '';
    const query = searchQuery || document.getElementById('history-search')?.value || '';
    const container = document.getElementById('history-container');
    try {
        let url = filter ? `/api/history?type=${filter}` : '/api/history';
        if (query) url += `${url.includes('?') ? '&' : '?'}q=${encodeURIComponent(query)}`;
        const res = await API.get(url);
        if (res.status === 'success' && res.data.length > 0) {
            // Sort: favorites first
            const sorted = [...res.data].sort((a, b) => (b.is_favorite ? 1 : 0) - (a.is_favorite ? 1 : 0));
            container.innerHTML = `
                <table class="history-table">
                    <thead><tr><th></th><th></th><th>ID</th><th>Type</th><th>Name</th><th>Seed</th><th>Date</th><th>Actions</th></tr></thead>
                    <tbody>
                        ${sorted.map(sim => `
                            <tr style="cursor:pointer" onclick="showHistoryDetail(${sim.id})">
                                <td onclick="event.stopPropagation()">
                                    <input type="checkbox" class="report-cb" onchange="toggleReportSelection(${sim.id}, this)" />
                                </td>
                                <td onclick="event.stopPropagation()">
                                    <button class="fav-star-btn ${sim.is_favorite ? 'active' : ''}" onclick="toggleFavorite(${sim.id}, event)" title="${sim.is_favorite ? 'Unfavorite' : 'Favorite'}">
                                        ${sim.is_favorite ? '★' : '☆'}
                                    </button>
                                </td>
                                <td style="font-family:var(--font-mono);color:var(--text-tertiary);">#${sim.id}</td>
                                <td><span class="history-type-badge badge-${sim.sim_type}">${sim.sim_type}</span></td>
                                <td>${sim.name || 'Unnamed'}</td>
                                <td style="font-family:var(--font-mono);font-size:11px;color:var(--text-tertiary);">${sim.seed || '—'}</td>
                                <td style="font-size:12px;color:var(--text-tertiary);">${new Date(sim.created_at).toLocaleString()}</td>
                                <td onclick="event.stopPropagation()">
                                    <button class="btn btn-secondary btn-sm" onclick="exportSimulation(${sim.id})">JSON</button>
                                    <button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/${sim.id}/csv')" style="margin-left:2px;">CSV</button>
                                    ${sim.sim_type === 'ber' ? `<button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/${sim.id}/latex')" style="margin-left:2px;">LaTeX</button>` : ''}
                                    <button class="btn btn-secondary btn-sm" onclick="deleteSimulation(${sim.id})" style="margin-left:2px;">🗑️</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>`;
        } else {
            container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📋</div><div class="empty-state-title">No Simulations Found</div></div>`;
        }
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-title">Failed to load history</div></div>`;
    }
};


// ═══════════════════════════════════════════════════════════════════════════
//  SSE Live BER Streaming
// ═══════════════════════════════════════════════════════════════════════════

async function runBerSimulationStreaming() {
    const btn = document.getElementById('btn-run-ber');
    btn.disabled = true;
    setLoading('ber-loading', true);

    // Show progress panel, hide spinner fallback
    const progressPanel = document.getElementById('ber-progress-panel');
    const spinnerFallback = document.getElementById('ber-spinner-fallback');
    if (progressPanel) progressPanel.style.display = 'block';
    if (spinnerFallback) spinnerFallback.style.display = 'none';

    const params = {
        modulation: document.getElementById('ber-modulation').value,
        channel: document.getElementById('ber-channel').value,
        coding: document.getElementById('ber-coding').value,
        snr_min: document.getElementById('ber-snr-min').value,
        snr_max: document.getElementById('ber-snr-max').value,
        snr_step: document.getElementById('ber-snr-step').value,
        num_bits: document.getElementById('ber-num-bits').value,
        min_errors: document.getElementById('ber-min-errors')?.value || 100,
        max_iterations: document.getElementById('ber-max-iter')?.value || 50,
        seed: document.getElementById('ber-seed')?.value || 'auto',
        num_tx: document.getElementById('ber-num-tx')?.value || 1,
        num_rx: document.getElementById('ber-num-rx')?.value || 1
    };

    try {
        const response = await fetch('/api/simulate/ber-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let lastData = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const event = JSON.parse(line.slice(6));
                        handleStreamEvent(event);
                        lastData = event;
                    } catch (e) { /* skip parse error */ }
                }
            }
        }

        // Final result
        if (lastData && lastData.type === 'complete') {
            const data = lastData.data;
            displayBerResults(data);
            SessionStats.increment(data.metadata?.elapsed_seconds || 0);
            showToast('BER simulation completed!', 'success');
        } else if (lastData && lastData.type === 'error') {
            showToast(`Error: ${lastData.message}`, 'error');
        }
    } catch (e) {
        showToast(`Streaming failed: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        setLoading('ber-loading', false);
        if (progressPanel) progressPanel.style.display = 'none';
        if (spinnerFallback) spinnerFallback.style.display = '';
    }
}

function handleStreamEvent(event) {
    const fillEl = document.getElementById('ber-progress-fill');
    const textEl = document.getElementById('ber-progress-text');
    const etaEl = document.getElementById('ber-progress-eta');
    const detailEl = document.getElementById('ber-progress-detail');

    if (event.type === 'progress') {
        const pct = Math.round(event.progress * 100);
        if (fillEl) fillEl.style.width = `${pct}%`;
        if (textEl) textEl.textContent = `SNR ${event.snr_db} dB — ${pct}% complete`;
        if (etaEl && event.eta_seconds) {
            const eta = Math.round(event.eta_seconds);
            etaEl.textContent = eta > 60 ? `~${(eta / 60).toFixed(1)}m remaining` : `~${eta}s remaining`;
        }
        if (detailEl && event.current_ber !== undefined) {
            detailEl.textContent = `BER: ${event.current_ber > 0 ? event.current_ber.toExponential(2) : '0'} | Point ${event.point_index + 1}/${event.total_points}`;
        }
    } else if (event.type === 'init') {
        if (textEl) textEl.textContent = `Initializing ${event.total_points} SNR points...`;
        if (fillEl) fillEl.style.width = '0%';
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Keyboard Shortcut Help
// ═══════════════════════════════════════════════════════════════════════════

function closeShortcutHelp(event) {
    if (event.target.id === 'shortcut-help-modal') {
        document.getElementById('shortcut-help-modal').style.display = 'none';
    }
}

function openShortcutHelp() {
    const modal = document.getElementById('shortcut-help-modal');
    if (modal) modal.style.display = 'flex';
}


// ═══════════════════════════════════════════════════════════════════════════
//  Override BER Run Button to Use Streaming
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    // Replace the BER run button to use streaming
    const berBtn = document.getElementById('btn-run-ber');
    if (berBtn) {
        berBtn.onclick = runBerSimulationStreaming;
    }

    // Load favorites count
    loadFavoritesCount();

    // Add `?` shortcut for help overlay
    document.addEventListener('keydown', (e) => {
        // `?` key (Shift + /)
        if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
            const activeEl = document.activeElement;
            if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.tagName === 'SELECT')) return;
            e.preventDefault();
            openShortcutHelp();
        }
        // Escape to close shortcut help
        if (e.key === 'Escape') {
            const modal = document.getElementById('shortcut-help-modal');
            if (modal && modal.style.display === 'flex') {
                modal.style.display = 'none';
            }
        }
    });

    // Update session stats periodically
    SessionStats._update();
});
