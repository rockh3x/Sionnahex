/**
 * Sionnah3x Research Assistant — Application Logic
 * Handles navigation, API communication, simulation runs, and visualization.
 */

// ═══════════════════════════════════════════════════════════════════════════
//  API Layer
// ═══════════════════════════════════════════════════════════════════════════

const API = {
    base: '',

    async get(path) {
        const res = await fetch(`${this.base}${path}`);
        return res.json();
    },

    async post(path, data) {
        const res = await fetch(`${this.base}${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return res.json();
    },

    async del(path) {
        const res = await fetch(`${this.base}${path}`, { method: 'DELETE' });
        return res.json();
    }
};


// ═══════════════════════════════════════════════════════════════════════════
//  Navigation
// ═══════════════════════════════════════════════════════════════════════════

function navigateTo(pageId) {
    // Update nav active states
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageId);
    });

    // Show target page, hide all others
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
        page.style.display = '';
        page.style.opacity = '';
    });
    const target = document.getElementById(`page-${pageId}`);
    if (target) {
        target.classList.add('active');
    }

    // Load data for specific pages
    if (pageId === 'history') loadHistory();
    if (pageId === 'dashboard') loadDashboard();
    if (pageId === 'compare') { if (typeof loadCompareSimulations === 'function') loadCompareSimulations(); }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Toast Notifications
// ═══════════════════════════════════════════════════════════════════════════

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span> ${message}`;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(12px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}


// ═══════════════════════════════════════════════════════════════════════════
//  Loading States
// ═══════════════════════════════════════════════════════════════════════════

function setLoading(id, active) {
    const overlay = document.getElementById(id);
    if (overlay) overlay.classList.toggle('active', active);
}


// ═══════════════════════════════════════════════════════════════════════════
//  System Info / Dashboard
// ═══════════════════════════════════════════════════════════════════════════

async function loadSystemInfo() {
    try {
        const info = await API.get('/api/system-info');
        updateSystemStatus(info);
        updateDashboard(info);
    } catch (e) {
        console.error('Failed to load system info:', e);
    }
}

function updateSystemStatus(info) {
    const sionnaEl = document.getElementById('status-sionna');
    const pytorchEl = document.getElementById('status-pytorch');
    const deviceEl = document.getElementById('status-device');

    if (info.sionna_available) {
        sionnaEl.className = 'status-badge online';
        sionnaEl.textContent = `v${info.sionna_version}`;
    } else {
        sionnaEl.className = 'status-badge offline';
        sionnaEl.textContent = 'Fallback';
    }

    if (info.pytorch_available) {
        pytorchEl.className = 'status-badge online';
        pytorchEl.textContent = `v${info.pytorch_version}`;
    } else {
        pytorchEl.className = 'status-badge offline';
        pytorchEl.textContent = 'N/A';
    }

    deviceEl.textContent = info.device === 'cuda' ? '🟢 GPU' : '🔵 CPU';
}

function updateDashboard(info) {
    document.getElementById('dash-total-sims').textContent = info.simulation_counts?.total || 0;
    document.getElementById('dash-engine').textContent = info.sionna_available ? 'Sionna' : 'NumPy';
    document.getElementById('dash-gpu').textContent = info.gpu_name || 'CPU Mode';
    document.getElementById('dash-python').textContent = info.python_version || '—';
}

async function loadDashboard() {
    await loadSystemInfo();
    await loadRecentSimulations();
    if (typeof loadAnalytics === 'function') loadAnalytics();
}


// ═══════════════════════════════════════════════════════════════════════════
//  BER Simulation
// ═══════════════════════════════════════════════════════════════════════════

let berChart = null;
let comparisonDatasets = [];
let comparisonChart = null;
const COMPARISON_COLORS = ['#76B900','#00d4ff','#ff6b35','#a855f7','#ec4899','#f59e0b','#10b981','#6366f1'];

async function runBerSimulation() {
    const btn = document.getElementById('btn-run-ber');
    btn.disabled = true;
    setLoading('ber-loading', true);

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
        const res = await API.post('/api/simulate/ber', params);

        if (res.status === 'success') {
            displayBerResults(res.data);
            showToast('BER simulation completed!', 'success');
        } else {
            showToast(`Error: ${res.message}`, 'error');
        }
    } catch (e) {
        showToast(`Simulation failed: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        setLoading('ber-loading', false);
    }
}

function displayBerResults(data) {
    const container = document.getElementById('ber-results-container');
    const meta = data.metadata;
    const hasTheo = data.theoretical_ber && data.theoretical_ber.length > 0;
    const hasCI = data.confidence_intervals && data.confidence_intervals.length > 0;
    const hasStats = data.statistics && data.statistics.length > 0;
    const mimoStr = (meta.num_tx > 1 || meta.num_rx > 1) ? ` ${meta.num_tx}×${meta.num_rx}` : '';

    container.innerHTML = `
        <div class="section-title">📊 BER vs SNR — ${meta.modulation.toUpperCase()}${mimoStr} / ${meta.channel.toUpperCase()} / ${meta.coding.toUpperCase()}</div>
        <div class="plot-container">
            <button class="plot-download-btn" onclick="downloadCanvas('ber-chart','BER_${meta.modulation}_${meta.channel}')">📥 PNG</button>
            <canvas id="ber-chart" height="320"></canvas>
        </div>
        <div style="display:flex;gap:8px;margin:8px 0 16px;">
            <button class="btn btn-secondary btn-sm" onclick="addToComparison()">➕ Add to Comparison</button>
            <button class="btn btn-secondary btn-sm" onclick="exportCurrentBerCSV()">📄 CSV</button>
            <button class="btn btn-secondary btn-sm" onclick="exportCurrentBerLatex()">📝 LaTeX</button>
        </div>

        <div class="section-title">📈 Throughput vs Shannon Capacity</div>
        <div class="plot-container">
            <button class="plot-download-btn" onclick="downloadCanvas('throughput-chart','Throughput')">📥 PNG</button>
            <canvas id="throughput-chart" height="220"></canvas>
        </div>

        ${hasStats ? `
        <div class="section-title">🔬 Statistical Detail (per SNR point)</div>
        <div class="stats-detail-grid">
            ${data.statistics.map(s => `
                <div class="stats-detail-item">
                    <span class="label">${s.snr_db} dB</span>
                    <span class="value">${s.total_errors} errs / ${(s.total_bits/1000).toFixed(0)}k bits (${s.iterations} iter)</span>
                </div>
            `).join('')}
        </div>` : ''}

        ${hasTheo && data.theoretical_info ? `
        <div class="reference-box">
            <div class="ref-title">📖 Theoretical Reference</div>
            <div class="ref-formula">${data.theoretical_info.formula}</div>
            <div class="ref-citation">${data.theoretical_info.reference}</div>
        </div>` : ''}

        <div class="section-title" style="margin-top:20px;">📋 Simulation Metadata</div>
        <div class="metrics-grid">
            <div class="metric-item"><div class="metric-value">${meta.modulation.toUpperCase()}</div><div class="metric-label">Modulation</div></div>
            <div class="metric-item"><div class="metric-value">${meta.channel.toUpperCase()}</div><div class="metric-label">Channel</div></div>
            <div class="metric-item"><div class="metric-value">${meta.coding.toUpperCase()}</div><div class="metric-label">Coding</div></div>
            <div class="metric-item"><div class="metric-value">${meta.elapsed_seconds}s</div><div class="metric-label">Runtime</div></div>
            <div class="metric-item"><div class="metric-value">${meta.num_tx||1}×${meta.num_rx||1}</div><div class="metric-label">MIMO</div></div>
            <div class="metric-item"><div class="metric-value">${meta.seed}</div><div class="metric-label">Seed</div></div>
        </div>

        <div class="section-title" style="margin-top:20px;">📝 Research Notes</div>
        <textarea class="notes-textarea" id="ber-notes" placeholder="Add notes about this simulation (e.g., 'Figure 3 in Chapter 4')..." oninput="saveNotesDebounced(${data.sim_id})"></textarea>

        ${typeof renderPerfWidget === 'function' ? renderPerfWidget(data.metadata) : ''}
    `;

    // Store last data for comparison
    window._lastBerData = data;

    // BER Chart with theoretical + CI
    const ctx = document.getElementById('ber-chart').getContext('2d');
    if (berChart) berChart.destroy();

    const datasets = [{
        label: 'BER (Simulated)',
        data: data.ber_values,
        borderColor: '#76B900',
        backgroundColor: 'rgba(118, 185, 0, 0.1)',
        borderWidth: 2.5,
        pointRadius: 5,
        pointBackgroundColor: '#76B900',
        pointBorderColor: '#fff',
        pointBorderWidth: 1,
        pointStyle: 'circle',
        fill: false,
        tension: 0.1
    }];

    if (hasTheo) {
        datasets.push({
            label: 'BER (Theoretical)',
            data: data.theoretical_ber,
            borderColor: '#ff6b35',
            borderWidth: 2,
            pointRadius: 0,
            borderDash: [8, 4],
            fill: false,
            tension: 0.3
        });
    }

    if (hasCI) {
        datasets.push({
            label: '95% CI Upper',
            data: data.confidence_intervals.map(c => c.upper),
            borderColor: 'rgba(118,185,0,0.2)',
            backgroundColor: 'rgba(118,185,0,0.05)',
            borderWidth: 1,
            pointRadius: 0,
            fill: '+1',
            tension: 0.1
        });
        datasets.push({
            label: '95% CI Lower',
            data: data.confidence_intervals.map(c => c.lower || 1e-15),
            borderColor: 'rgba(118,185,0,0.2)',
            borderWidth: 1,
            pointRadius: 0,
            fill: false,
            tension: 0.1
        });
    }

    datasets.push({
        label: 'BLER',
        data: data.bler_values,
        borderColor: '#00d4ff',
        borderWidth: 1.5,
        pointRadius: 3,
        pointBackgroundColor: '#00d4ff',
        borderDash: [3, 3],
        fill: false,
        tension: 0.3
    });

    berChart = new Chart(ctx, {
        type: 'line',
        data: { labels: data.snr_values.map(v => `${v}`), datasets },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { labels: { color: '#aaa', font: { family: 'Inter', size: 11 } } },
                tooltip: { backgroundColor: '#1a1a2e', titleColor: '#fff', bodyColor: '#ccc', borderColor: '#333', borderWidth: 1 }
            },
            scales: {
                x: { title: { display: true, text: 'Eb/N0 (dB)', color: '#888' }, ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { type: 'logarithmic', title: { display: true, text: 'Bit Error Rate', color: '#888' }, ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' }, min: 1e-7 }
            }
        }
    });

    // Throughput + Shannon
    const ctx2 = document.getElementById('throughput-chart').getContext('2d');
    const tpDatasets = [{
        label: 'Throughput (Simulated)',
        data: data.throughput,
        borderColor: '#76B900',
        backgroundColor: 'rgba(118, 185, 0, 0.1)',
        borderWidth: 2.5, pointRadius: 4, pointBackgroundColor: '#76B900',
        fill: true, tension: 0.3
    }];
    if (data.shannon_capacity) {
        tpDatasets.push({
            label: 'Shannon Capacity',
            data: data.shannon_capacity,
            borderColor: '#ff6b35',
            borderWidth: 2, pointRadius: 0, borderDash: [8, 4], fill: false, tension: 0.3
        });
    }
    new Chart(ctx2, {
        type: 'line',
        data: { labels: data.snr_values.map(v => `${v}`), datasets: tpDatasets },
        options: {
            responsive: true,
            plugins: { legend: { labels: { color: '#aaa', font: { family: 'Inter' } } }, tooltip: { backgroundColor: '#1a1a2e', titleColor: '#fff', bodyColor: '#ccc', borderColor: '#333', borderWidth: 1 } },
            scales: {
                x: { title: { display: true, text: 'SNR (dB)', color: '#888' }, ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' } },
                y: { title: { display: true, text: 'bits/s/Hz', color: '#888' }, ticks: { color: '#666' }, grid: { color: 'rgba(255,255,255,0.04)' } }
            }
        }
    });
}


// ═══════════════════════════════════════════════════════════════════════════
//  Constellation Simulation
// ═══════════════════════════════════════════════════════════════════════════

async function runConstellationSimulation() {
    const btn = document.getElementById('btn-run-const');
    btn.disabled = true;
    setLoading('const-loading', true);

    const params = {
        modulation: document.getElementById('const-modulation').value,
        channel: document.getElementById('const-channel').value,
        snr_db: document.getElementById('const-snr').value,
        num_symbols: document.getElementById('const-symbols').value,
        seed: document.getElementById('const-seed')?.value || 'auto'
    };

    try {
        const res = await API.post('/api/simulate/constellation', params);
        if (res.status === 'success') {
            displayConstellationResults(res.data);
            showToast('Constellation generated!', 'success');
        } else {
            showToast(`Error: ${res.message}`, 'error');
        }
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        setLoading('const-loading', false);
    }
}

function displayConstellationResults(data) {
    const container = document.getElementById('const-results-container');
    container.innerHTML = `
        <div class="section-title">🔵 Constellation Diagram</div>
        <div class="plot-container">
            <img src="data:image/png;base64,${data.plot}" alt="Constellation Diagram" />
        </div>

        <div class="section-title">📋 EVM Metrics</div>
        <div class="metrics-grid">
            <div class="metric-item">
                <div class="metric-value">${data.evm_percent}%</div>
                <div class="metric-label">EVM (RMS)</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${data.evm_db} dB</div>
                <div class="metric-label">EVM (dB)</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${data.metadata.modulation.toUpperCase()}</div>
                <div class="metric-label">Modulation</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${data.metadata.snr_db} dB</div>
                <div class="metric-label">SNR</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${data.num_symbols}</div>
                <div class="metric-label">Symbols</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${data.metadata.elapsed_seconds}s</div>
                <div class="metric-label">Runtime</div>
            </div>
        </div>
    `;
}


// ═══════════════════════════════════════════════════════════════════════════
//  Channel Simulation
// ═══════════════════════════════════════════════════════════════════════════

async function runChannelSimulation() {
    const btn = document.getElementById('btn-run-channel');
    btn.disabled = true;
    setLoading('channel-loading', true);

    const params = {
        model: document.getElementById('ch-model').value,
        delay_spread_ns: document.getElementById('ch-delay-spread').value,
        num_subcarriers: document.getElementById('ch-subcarriers').value,
        subcarrier_spacing_khz: document.getElementById('ch-scs').value,
        num_realizations: document.getElementById('ch-realizations').value,
        seed: document.getElementById('ch-seed')?.value || 'auto'
    };

    try {
        const res = await API.post('/api/simulate/channel', params);
        if (res.status === 'success') {
            displayChannelResults(res.data);
            showToast('Channel simulation complete!', 'success');
        } else {
            showToast(`Error: ${res.message}`, 'error');
        }
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        setLoading('channel-loading', false);
    }
}

function displayChannelResults(data) {
    const container = document.getElementById('channel-results-container');
    const stats = data.statistics;

    container.innerHTML = `
        <div class="section-title">📡 Channel Impulse Response</div>
        <div class="plot-container">
            <img src="data:image/png;base64,${data.cir_plot}" alt="Channel Impulse Response" />
        </div>

        <div class="section-title">📊 Frequency Response</div>
        <div class="plot-container">
            <img src="data:image/png;base64,${data.freq_plot}" alt="Frequency Response" />
        </div>

        <div class="section-title">⚡ Power Delay Profile</div>
        <div class="plot-container">
            <img src="data:image/png;base64,${data.pdp_plot}" alt="Power Delay Profile" />
        </div>

        <div class="section-title">📋 Channel Statistics</div>
        <div class="metrics-grid">
            <div class="metric-item">
                <div class="metric-value">${stats.model}</div>
                <div class="metric-label">Model</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${stats.rms_delay_spread_ns} ns</div>
                <div class="metric-label">RMS Delay Spread</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${stats.coherence_bandwidth_mhz} MHz</div>
                <div class="metric-label">Coherence BW</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${stats.num_taps}</div>
                <div class="metric-label">Channel Taps</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${stats.max_delay_ns} ns</div>
                <div class="metric-label">Max Delay</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${data.metadata.elapsed_seconds}s</div>
                <div class="metric-label">Runtime</div>
            </div>
        </div>
    `;
}


// ═══════════════════════════════════════════════════════════════════════════
//  OFDM Simulation
// ═══════════════════════════════════════════════════════════════════════════

async function runOfdmSimulation() {
    const btn = document.getElementById('btn-run-ofdm');
    btn.disabled = true;
    setLoading('ofdm-loading', true);

    const params = {
        num_subcarriers: document.getElementById('ofdm-sc').value,
        cp_length: document.getElementById('ofdm-cp').value,
        modulation: document.getElementById('ofdm-mod').value,
        channel_model: document.getElementById('ofdm-channel').value,
        snr_db: document.getElementById('ofdm-snr').value,
        num_symbols: document.getElementById('ofdm-symbols').value,
        pilot_spacing: document.getElementById('ofdm-pilot').value,
        seed: document.getElementById('ofdm-seed')?.value || 'auto'
    };

    try {
        const res = await API.post('/api/simulate/ofdm', params);
        if (res.status === 'success') {
            displayOfdmResults(res.data);
            showToast('OFDM simulation complete!', 'success');
        } else {
            showToast(`Error: ${res.message}`, 'error');
        }
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        setLoading('ofdm-loading', false);
    }
}

function displayOfdmResults(data) {
    const container = document.getElementById('ofdm-results-container');
    const m = data.metrics;
    const ber = data.ber_by_equalizer;

    container.innerHTML = `
        <div class="section-title">📊 Channel Frequency Response</div>
        <div class="plot-container">
            <img src="data:image/png;base64,${data.spectrum_plot}" alt="OFDM Spectrum" />
        </div>

        <div class="section-title">🔵 Equalizer Comparison (ZF vs MMSE vs LMMSE)</div>
        <div class="plot-container">
            <img src="data:image/png;base64,${data.eq_comparison_plot}" alt="Equalizer Comparison" />
        </div>

        <div class="section-title">📶 Resource Grid</div>
        <div class="plot-container">
            <img src="data:image/png;base64,${data.resource_grid_plot}" alt="Resource Grid" />
        </div>

        <div class="section-title">📡 Channel Estimation</div>
        <div class="plot-container">
            <img src="data:image/png;base64,${data.channel_est_plot}" alt="Channel Estimation" />
        </div>

        <div class="section-title">📋 OFDM Metrics</div>
        <div class="metrics-grid">
            <div class="metric-item">
                <div class="metric-value">${m.num_subcarriers}</div>
                <div class="metric-label">Subcarriers</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${m.num_data_subcarriers}</div>
                <div class="metric-label">Data SCs</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${m.num_pilots}</div>
                <div class="metric-label">Pilots</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${m.pilot_overhead_percent}%</div>
                <div class="metric-label">Pilot Overhead</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${m.cp_overhead_percent}%</div>
                <div class="metric-label">CP Overhead</div>
            </div>
            <div class="metric-item">
                <div class="metric-value">${m.spectral_efficiency}</div>
                <div class="metric-label">Spectral Eff.</div>
            </div>
        </div>

        <div class="section-title" style="margin-top:20px;">⚡ BER by Equalizer</div>
        <div class="metrics-grid">
            <div class="metric-item">
                <div class="metric-value" style="color:#00d4ff;">${ber.zf !== undefined ? ber.zf.toExponential(2) : 'N/A'}</div>
                <div class="metric-label">Zero-Forcing</div>
            </div>
            <div class="metric-item">
                <div class="metric-value" style="color:#76B900;">${ber.mmse !== undefined ? ber.mmse.toExponential(2) : 'N/A'}</div>
                <div class="metric-label">MMSE</div>
            </div>
            <div class="metric-item">
                <div class="metric-value" style="color:#ff6b35;">${ber.lmmse !== undefined ? ber.lmmse.toExponential(2) : 'N/A'}</div>
                <div class="metric-label">LMMSE</div>
            </div>
            <div class="metric-item">
                <div class="metric-value" style="color:#a855f7;">${m.best_equalizer.toUpperCase()}</div>
                <div class="metric-label">Best Equalizer</div>
            </div>
        </div>
    `;
}


// ═══════════════════════════════════════════════════════════════════════════
//  BER Comparison Overlay
// ═══════════════════════════════════════════════════════════════════════════

function addToComparison() {
    const data = window._lastBerData;
    if (!data) return showToast('No BER data to add', 'error');
    if (comparisonDatasets.length >= 8) return showToast('Max 8 curves', 'error');
    const m = data.metadata;
    const label = `${m.modulation.toUpperCase()}/${m.channel.toUpperCase()}/${m.coding.toUpperCase()}`;
    const color = COMPARISON_COLORS[comparisonDatasets.length % COMPARISON_COLORS.length];
    comparisonDatasets.push({ data, label, color });
    renderComparison();
    showToast(`Added "${label}" to comparison`, 'success');
}

function renderComparison() {
    const card = document.getElementById('comparison-card');
    if (comparisonDatasets.length === 0) { card.style.display = 'none'; return; }
    card.style.display = 'block';
    const ctx = document.getElementById('comparison-chart').getContext('2d');
    if (comparisonChart) comparisonChart.destroy();
    const datasets = [];
    comparisonDatasets.forEach((ds, i) => {
        datasets.push({
            label: `${ds.label} (Sim)`, data: ds.data.ber_values,
            borderColor: ds.color, borderWidth: 2, pointRadius: 4,
            pointBackgroundColor: ds.color, fill: false, tension: 0.1
        });
        if (ds.data.theoretical_ber) {
            datasets.push({
                label: `${ds.label} (Theo)`, data: ds.data.theoretical_ber,
                borderColor: ds.color, borderWidth: 1.5, borderDash: [6, 3],
                pointRadius: 0, fill: false, tension: 0.3
            });
        }
    });
    const labels = comparisonDatasets[0].data.snr_values.map(v => `${v}`);
    comparisonChart = new Chart(ctx, {
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
    const legend = document.getElementById('comparison-legend');
    legend.innerHTML = comparisonDatasets.map((ds, i) =>
        `<div class="comparison-legend-item"><span class="dot" style="background:${ds.color}"></span>${ds.label}</div>`
    ).join('');
}

function clearComparison() {
    comparisonDatasets = [];
    if (comparisonChart) { comparisonChart.destroy(); comparisonChart = null; }
    document.getElementById('comparison-card').style.display = 'none';
    showToast('Comparison cleared', 'info');
}


// ═══════════════════════════════════════════════════════════════════════════
//  Parameter Sweep
// ═══════════════════════════════════════════════════════════════════════════

async function runBerSweep() {
    const cbs = document.querySelectorAll('.sweep-mod-cb:checked');
    const mods = Array.from(cbs).map(cb => cb.value);
    if (mods.length < 2) return showToast('Select at least 2 modulations', 'error');
    setLoading('ber-loading', true);
    try {
        const params = {
            sweep_param: 'modulation', sweep_values: mods,
            channel: document.getElementById('ber-channel').value,
            coding: document.getElementById('ber-coding').value,
            snr_min: document.getElementById('ber-snr-min').value,
            snr_max: document.getElementById('ber-snr-max').value,
            snr_step: document.getElementById('ber-snr-step').value,
            num_bits: document.getElementById('ber-num-bits').value,
            min_errors: document.getElementById('ber-min-errors')?.value || 100,
            max_iterations: document.getElementById('ber-max-iter')?.value || 50,
            seed: document.getElementById('ber-seed')?.value || 'auto'
        };
        const res = await API.post('/api/simulate/ber-sweep', params);
        if (res.status === 'success') {
            comparisonDatasets = [];
            res.data.forEach((d, i) => {
                comparisonDatasets.push({
                    data: d, label: d.label || mods[i].toUpperCase(),
                    color: COMPARISON_COLORS[i % COMPARISON_COLORS.length]
                });
            });
            if (res.data.length > 0) { window._lastBerData = res.data[0]; displayBerResults(res.data[0]); }
            renderComparison();
            // Generate heatmap
            if (typeof generateHeatmap === 'function') {
                const heatData = res.data.map(d => ({ label: d.label, snr_values: d.snr_values, ber_values: d.ber_values }));
                generateHeatmap(heatData);
            }
            showToast(`Sweep complete: ${mods.length} modulations`, 'success');
        } else { showToast(`Error: ${res.message}`, 'error'); }
    } catch (e) { showToast(`Sweep failed: ${e.message}`, 'error'); }
    finally { setLoading('ber-loading', false); }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Download / Export Helpers
// ═══════════════════════════════════════════════════════════════════════════

function downloadCanvas(canvasId, name) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `${name}_${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png', 1.0);
    link.click();
    showToast('Chart downloaded as PNG', 'success');
}

function downloadBase64Image(b64, name) {
    const link = document.createElement('a');
    link.download = `${name}_${Date.now()}.png`;
    link.href = `data:image/png;base64,${b64}`;
    link.click();
    showToast('Plot downloaded as PNG', 'success');
}

function exportCurrentBerCSV() {
    const data = window._lastBerData;
    if (!data?.sim_id) return showToast('No simulation to export', 'error');
    window.open(`/api/export/${data.sim_id}/csv`, '_blank');
}

function exportCurrentBerLatex() {
    const data = window._lastBerData;
    if (!data?.sim_id) return showToast('No simulation to export', 'error');
    window.open(`/api/export/${data.sim_id}/latex`, '_blank');
}


// ═══════════════════════════════════════════════════════════════════════════
//  Research Notes
// ═══════════════════════════════════════════════════════════════════════════

let _notesTimer = null;
function saveNotesDebounced(simId) {
    clearTimeout(_notesTimer);
    _notesTimer = setTimeout(async () => {
        const el = document.getElementById('ber-notes');
        if (!el) return;
        try {
            await API.post(`/api/history/${simId}/notes`, { notes: el.value, tags: '' });
        } catch (e) { /* silent */ }
    }, 1500);
}

// Make PATCH work through our API layer
const _origPost = API.post.bind(API);
API.patch = async function(path, data) {
    const res = await fetch(`${this.base}${path}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return res.json();
};
// Override saveNotes to use PATCH
async function saveNotes(simId, notes, tags) {
    try { await API.patch(`/api/history/${simId}/notes`, { notes, tags }); }
    catch (e) { /* silent */ }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Dashboard — Recent Simulations
// ═══════════════════════════════════════════════════════════════════════════

async function loadRecentSimulations() {
    const container = document.getElementById('recent-sims-container');
    if (!container) return;
    try {
        const res = await API.get('/api/history?limit=5');
        if (res.status === 'success' && res.data.length > 0) {
            const icons = { ber: '📊', constellation: '🔵', channel: '📡', ofdm: '📶' };
            container.innerHTML = res.data.map(sim => `
                <div class="recent-sim-item" onclick="navigateTo('${sim.sim_type === 'ber' ? 'ber' : sim.sim_type}')">
                    <div class="recent-sim-icon ${sim.sim_type}">${icons[sim.sim_type] || '📋'}</div>
                    <div class="recent-sim-info">
                        <div class="recent-sim-name">${sim.name || 'Unnamed'}</div>
                        <div class="recent-sim-time">${new Date(sim.created_at).toLocaleString()}</div>
                    </div>
                    <span class="history-type-badge badge-${sim.sim_type}">${sim.sim_type}</span>
                </div>
            `).join('');
        }
    } catch (e) { /* silent */ }
}


// ═══════════════════════════════════════════════════════════════════════════
//  History (updated with CSV/LaTeX export buttons)
// ═══════════════════════════════════════════════════════════════════════════

async function loadHistory(searchQuery) {
    const filter = document.getElementById('history-filter')?.value || '';
    const query = searchQuery || document.getElementById('history-search')?.value || '';
    const container = document.getElementById('history-container');
    try {
        let url = filter ? `/api/history?type=${filter}` : '/api/history';
        if (query) url += `${url.includes('?') ? '&' : '?'}q=${encodeURIComponent(query)}`;
        const res = await API.get(url);
        if (res.status === 'success' && res.data.length > 0) {
            container.innerHTML = `
                <table class="history-table">
                    <thead><tr><th></th><th>ID</th><th>Type</th><th>Name</th><th>Seed</th><th>Date</th><th>Actions</th></tr></thead>
                    <tbody>
                        ${res.data.map(sim => `
                            <tr style="cursor:pointer" onclick="if(typeof showHistoryDetail==='function')showHistoryDetail(${sim.id})">
                                <td onclick="event.stopPropagation()">
                                    <input type="checkbox" class="report-cb" onchange="toggleReportSelection(${sim.id}, this)" />
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
}

async function exportSimulation(id) {
    try {
        const data = await API.get(`/api/export/${id}`);
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `simulation_${id}.json`; a.click();
        URL.revokeObjectURL(url);
        showToast('Exported as JSON!', 'success');
    } catch (e) { showToast('Export failed', 'error'); }
}

async function deleteSimulation(id) {
    if (!confirm('Delete this simulation?')) return;
    try {
        await API.del(`/api/history/${id}`);
        showToast('Simulation deleted', 'info');
        loadHistory();
    } catch (e) { showToast('Delete failed', 'error'); }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Initialization
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    loadSystemInfo();
    loadRecentSimulations();
});

