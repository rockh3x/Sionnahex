/**
 * Sionnah3x — Phase 3 Features
 * Theme toggle, SSE progress, presets, command palette, keyboard shortcuts,
 * history detail, heatmap, performance profiler
 */

// ═══════════════════════════════════════════════════════════════════════════
//  Theme Toggle
// ═══════════════════════════════════════════════════════════════════════════

function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.getElementById('theme-icon').textContent = next === 'light' ? '☀️' : '🌙';
    document.getElementById('theme-label').textContent = next === 'light' ? 'Light Mode' : 'Dark Mode';
}

function initTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    const iconEl = document.getElementById('theme-icon');
    const labelEl = document.getElementById('theme-label');
    if (iconEl) iconEl.textContent = saved === 'light' ? '☀️' : '🌙';
    if (labelEl) labelEl.textContent = saved === 'light' ? 'Light Mode' : 'Dark Mode';
}


// ═══════════════════════════════════════════════════════════════════════════
//  SSE Streaming BER Simulation
// ═══════════════════════════════════════════════════════════════════════════

async function runBerSimulationStreaming() {
    const btn = document.getElementById('btn-run-ber');
    btn.disabled = true;
    setLoading('ber-loading', true);

    // Show progress panel, hide spinner
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

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const event = JSON.parse(line.substring(6));
                        handleBerStreamEvent(event);
                    } catch (e) { /* skip parse errors */ }
                }
            }
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

function handleBerStreamEvent(event) {
    const fill = document.getElementById('ber-progress-fill');
    const text = document.getElementById('ber-progress-text');
    const eta = document.getElementById('ber-progress-eta');
    const detail = document.getElementById('ber-progress-detail');

    if (event.type === 'init') {
        if (text) text.textContent = `0/${event.total_points} SNR points`;
        if (fill) fill.style.width = '0%';
    } else if (event.type === 'progress') {
        const pct = Math.round((event.current_point / event.total_points) * 100);
        if (fill) fill.style.width = pct + '%';
        if (text) text.textContent = `${event.current_point}/${event.total_points} — ${event.snr_db} dB: BER=${event.ber.toExponential(1)} (${event.errors} errors)`;
        if (eta) eta.textContent = `ETA: ${event.eta_seconds}s`;
        if (detail) detail.textContent = `Elapsed: ${event.elapsed}s | ${event.iterations} iter | ${(event.bits/1000).toFixed(0)}k bits`;
    } else if (event.type === 'complete') {
        // Save to DB via regular endpoint
        saveBerStreamResult(event);
        displayBerResults(event);
        showToast('BER simulation completed!', 'success');
    } else if (event.type === 'error') {
        showToast(`Error: ${event.message}`, 'error');
    }
}

async function saveBerStreamResult(data) {
    try {
        const meta = data.metadata;
        const params = {
            modulation: meta.modulation, channel: meta.channel, coding: meta.coding,
            snr_min: data.snr_values[0], snr_max: data.snr_values[data.snr_values.length-1],
            num_bits: meta.num_bits_per_iter, seed: meta.seed
        };
        // We already have the full result, just need to save it
        const res = await API.post('/api/simulate/ber', params);
        if (res.status === 'success') data.sim_id = res.data.sim_id;
    } catch(e) { /* silent */ }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Simulation Presets
// ═══════════════════════════════════════════════════════════════════════════

const BUILTIN_PRESETS = {
    awgn_validation: {
        name: 'AWGN Theory Validation',
        modulation: 'qpsk', channel: 'awgn', coding: 'uncoded',
        snr_min: 0, snr_max: 20, snr_step: 1, num_bits: 500000,
        min_errors: 200, max_iterations: 100, seed: '42',
        num_tx: 1, num_rx: 1
    },
    nr_baseline: {
        name: '3GPP NR Baseline',
        modulation: '16qam', channel: 'rayleigh', coding: 'ldpc',
        snr_min: 0, snr_max: 25, snr_step: 2, num_bits: 100000,
        min_errors: 100, max_iterations: 50, seed: 'auto',
        num_tx: 1, num_rx: 1
    },
    urban_mimo: {
        name: 'Urban Macro MIMO',
        modulation: 'qpsk', channel: 'rayleigh', coding: 'uncoded',
        snr_min: 0, snr_max: 25, snr_step: 2, num_bits: 100000,
        min_errors: 100, max_iterations: 50, seed: 'auto',
        num_tx: 4, num_rx: 4
    }
};

function loadPreset(simType) {
    const select = document.getElementById(`${simType}-preset`);
    if (!select) return;
    const key = select.value;
    if (!key) return;

    // Check built-in first, then user presets
    let preset = BUILTIN_PRESETS[key];
    if (!preset) {
        const userPresets = JSON.parse(localStorage.getItem('sim_presets') || '{}');
        preset = userPresets[key];
    }
    if (!preset) return;

    if (simType === 'ber') {
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        setVal('ber-modulation', preset.modulation);
        setVal('ber-channel', preset.channel);
        setVal('ber-coding', preset.coding);
        setVal('ber-snr-min', preset.snr_min);
        setVal('ber-snr-max', preset.snr_max);
        setVal('ber-snr-step', preset.snr_step);
        setVal('ber-num-bits', preset.num_bits);
        setVal('ber-min-errors', preset.min_errors);
        setVal('ber-max-iter', preset.max_iterations);
        setVal('ber-seed', preset.seed);
        setVal('ber-num-tx', preset.num_tx);
        setVal('ber-num-rx', preset.num_rx);
    }
    showToast(`Loaded preset: ${preset.name || key}`, 'success');
    select.value = '';
}

function savePreset(simType) {
    const name = prompt('Preset name:');
    if (!name) return;
    const key = 'user_' + name.toLowerCase().replace(/\s+/g, '_');

    let preset = {};
    if (simType === 'ber') {
        const getVal = (id) => document.getElementById(id)?.value || '';
        preset = {
            name, modulation: getVal('ber-modulation'), channel: getVal('ber-channel'),
            coding: getVal('ber-coding'), snr_min: getVal('ber-snr-min'),
            snr_max: getVal('ber-snr-max'), snr_step: getVal('ber-snr-step'),
            num_bits: getVal('ber-num-bits'), min_errors: getVal('ber-min-errors'),
            max_iterations: getVal('ber-max-iter'), seed: getVal('ber-seed'),
            num_tx: getVal('ber-num-tx'), num_rx: getVal('ber-num-rx')
        };
    }

    const userPresets = JSON.parse(localStorage.getItem('sim_presets') || '{}');
    userPresets[key] = preset;
    localStorage.setItem('sim_presets', JSON.stringify(userPresets));

    // Add to dropdown
    const select = document.getElementById(`${simType}-preset`);
    if (select && !select.querySelector(`option[value="${key}"]`)) {
        const opt = document.createElement('option');
        opt.value = key;
        opt.textContent = `📌 ${name}`;
        select.appendChild(opt);
    }
    showToast(`Preset "${name}" saved!`, 'success');
}

function loadUserPresets() {
    const userPresets = JSON.parse(localStorage.getItem('sim_presets') || '{}');
    const select = document.getElementById('ber-preset');
    if (!select) return;
    for (const [key, preset] of Object.entries(userPresets)) {
        const opt = document.createElement('option');
        opt.value = key;
        opt.textContent = `📌 ${preset.name || key}`;
        select.appendChild(opt);
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Command Palette
// ═══════════════════════════════════════════════════════════════════════════

const COMMANDS = [
    { icon: '🏠', label: 'Go to Dashboard', shortcut: 'Ctrl+1', action: () => navigateTo('dashboard') },
    { icon: '📊', label: 'Go to BER Analyzer', shortcut: 'Ctrl+2', action: () => navigateTo('ber') },
    { icon: '🔵', label: 'Go to Constellation', shortcut: 'Ctrl+3', action: () => navigateTo('constellation') },
    { icon: '📡', label: 'Go to Channel Explorer', shortcut: 'Ctrl+4', action: () => navigateTo('channel') },
    { icon: '📶', label: 'Go to OFDM Lab', shortcut: 'Ctrl+5', action: () => navigateTo('ofdm') },
    { icon: '📋', label: 'Go to History', shortcut: 'Ctrl+6', action: () => navigateTo('history') },
    { icon: 'ℹ️', label: 'About & Help', shortcut: '', action: () => navigateTo('about') },
    { icon: '⚡', label: 'Run BER Simulation', shortcut: 'Ctrl+Enter', action: () => { navigateTo('ber'); setTimeout(runBerSimulation, 100); } },
    { icon: '🔄', label: 'Run BER Sweep', shortcut: '', action: () => { navigateTo('ber'); setTimeout(runBerSweep, 100); } },
    { icon: '🌓', label: 'Toggle Theme', shortcut: '', action: () => toggleTheme() },
    { icon: '📄', label: 'Export Last BER as CSV', shortcut: 'Ctrl+E', action: () => exportCurrentBerCSV() },
    { icon: '📝', label: 'Export Last BER as LaTeX', shortcut: '', action: () => exportCurrentBerLatex() },
    { icon: '🔄', label: 'Refresh History', shortcut: '', action: () => { navigateTo('history'); loadHistory(); } },
];

function openCommandPalette() {
    const overlay = document.getElementById('command-palette');
    overlay.style.display = 'flex';
    const input = document.getElementById('command-input');
    input.value = '';
    input.focus();
    filterCommands('');
}

function closeCommandPalette(e) {
    if (!e || e.target.id === 'command-palette') {
        document.getElementById('command-palette').style.display = 'none';
    }
}

function filterCommands(query) {
    const list = document.getElementById('command-list');
    const q = query.toLowerCase();
    const filtered = COMMANDS.filter(c => c.label.toLowerCase().includes(q));
    list.innerHTML = filtered.map((cmd, i) =>
        `<div class="command-item${i===0?' active':''}" onclick="executeCommand(${COMMANDS.indexOf(cmd)})">
            <span class="cmd-icon">${cmd.icon}</span>
            <span class="cmd-label">${cmd.label}</span>
            <span class="cmd-shortcut">${cmd.shortcut}</span>
        </div>`
    ).join('');
}

function executeCommand(idx) {
    document.getElementById('command-palette').style.display = 'none';
    COMMANDS[idx]?.action();
}


// ═══════════════════════════════════════════════════════════════════════════
//  Keyboard Shortcuts
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('keydown', (e) => {
    // Ignore if typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        if (e.key === 'Escape') {
            closeCommandPalette(null);
            document.getElementById('history-detail-modal').style.display = 'none';
        }
        return;
    }

    if (e.ctrlKey || e.metaKey) {
        const pages = ['dashboard', 'ber', 'constellation', 'channel', 'ofdm', 'history'];
        const num = parseInt(e.key);
        if (num >= 1 && num <= 6) { e.preventDefault(); navigateTo(pages[num - 1]); return; }
        if (e.key === 'k' || e.key === 'K') { e.preventDefault(); openCommandPalette(); return; }
        if (e.key === 'Enter') { e.preventDefault(); runCurrentSimulation(); return; }
        if (e.key === 'e' || e.key === 'E') { e.preventDefault(); exportCurrentBerCSV(); return; }
    }

    if (e.key === 'Escape') {
        closeCommandPalette(null);
        document.getElementById('history-detail-modal').style.display = 'none';
    }
});

function runCurrentSimulation() {
    const activePage = document.querySelector('.page.active');
    if (!activePage) return;
    const id = activePage.id;
    if (id === 'page-ber') runBerSimulation();
    else if (id === 'page-constellation') runConstellationSimulation();
    else if (id === 'page-channel') runChannelSimulation();
    else if (id === 'page-ofdm') runOfdmSimulation();
}


// ═══════════════════════════════════════════════════════════════════════════
//  History Detail View & Re-Run
// ═══════════════════════════════════════════════════════════════════════════

async function showHistoryDetail(simId) {
    const modal = document.getElementById('history-detail-modal');
    const title = document.getElementById('history-detail-title');
    const body = document.getElementById('history-detail-body');
    body.innerHTML = '<div class="empty-state" style="padding:30px"><div class="spinner"></div></div>';
    modal.style.display = 'flex';

    try {
        const res = await API.get(`/api/history/${simId}`);
        if (res.status !== 'success') { body.innerHTML = '<p>Not found</p>'; return; }
        const sim = res.data;
        title.textContent = `#${sim.id} — ${sim.name || 'Unnamed'}`;

        const params = sim.parameters || {};
        const results = sim.results || {};
        const meta = results.metadata || {};

        let paramsHTML = Object.entries(params).map(([k,v]) =>
            `<div class="stats-detail-item"><span class="label">${k}</span><span class="value">${v}</span></div>`
        ).join('');

        body.innerHTML = `
            <div class="section-title">📋 Parameters</div>
            <div class="stats-detail-grid">${paramsHTML}</div>
            <div style="display:flex;gap:8px;margin:16px 0;">
                <button class="btn btn-primary btn-sm" onclick="rerunSimulation(${JSON.stringify(params).replace(/"/g,'&quot;')}, '${sim.sim_type}')">🔄 Re-Run</button>
                <button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/${sim.id}/csv')">📄 CSV</button>
                ${sim.sim_type === 'ber' ? `<button class="btn btn-secondary btn-sm" onclick="window.open('/api/export/${sim.id}/latex')">📝 LaTeX</button>` : ''}
                <button class="btn btn-secondary btn-sm" onclick="exportSimulation(${sim.id})">JSON</button>
            </div>
            ${sim.notes ? `<div class="section-title">📝 Notes</div><div class="reference-box"><div class="ref-formula">${sim.notes}</div></div>` : ''}
            <div class="section-title" style="margin-top:16px;">📊 Key Results</div>
            <div class="metrics-grid">
                ${meta.elapsed_seconds ? `<div class="metric-item"><div class="metric-value">${meta.elapsed_seconds}s</div><div class="metric-label">Runtime</div></div>` : ''}
                ${meta.engine ? `<div class="metric-item"><div class="metric-value">${meta.engine}</div><div class="metric-label">Engine</div></div>` : ''}
                ${meta.seed !== undefined ? `<div class="metric-item"><div class="metric-value">${meta.seed}</div><div class="metric-label">Seed</div></div>` : ''}
                ${results.ber_values ? `<div class="metric-item"><div class="metric-value">${Math.min(...results.ber_values.filter(b=>b>0)).toExponential(1)}</div><div class="metric-label">Min BER</div></div>` : ''}
            </div>
        `;
    } catch (e) {
        body.innerHTML = `<p style="color:var(--accent-warm)">Failed to load: ${e.message}</p>`;
    }
}

function rerunSimulation(params, simType) {
    document.getElementById('history-detail-modal').style.display = 'none';
    if (simType === 'ber') {
        navigateTo('ber');
        setTimeout(() => {
            const setVal = (id, val) => { const el = document.getElementById(id); if (el && val !== undefined) el.value = val; };
            setVal('ber-modulation', params.modulation);
            setVal('ber-channel', params.channel);
            setVal('ber-coding', params.coding);
            setVal('ber-snr-min', params.snr_min);
            setVal('ber-snr-max', params.snr_max);
            setVal('ber-snr-step', params.snr_step);
            setVal('ber-num-bits', params.num_bits);
            setVal('ber-seed', params.seed);
            showToast('Parameters loaded — click Run to execute', 'info');
        }, 200);
    } else {
        navigateTo(simType);
        showToast('Navigate to the simulation page to re-run', 'info');
    }
}

function closeHistoryDetail(e) {
    if (e.target.id === 'history-detail-modal') {
        document.getElementById('history-detail-modal').style.display = 'none';
    }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Heatmap Generation (after sweep)
// ═══════════════════════════════════════════════════════════════════════════

async function generateHeatmap(sweepResults) {
    if (!sweepResults || sweepResults.length < 2) return;
    try {
        const res = await fetch('/api/visualize/heatmap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sweep_results: sweepResults })
        });
        const data = await res.json();
        if (data.status === 'success') {
            const card = document.getElementById('heatmap-card');
            const container = document.getElementById('heatmap-container');
            if (card && container) {
                card.style.display = 'block';
                container.innerHTML = `<img src="data:image/png;base64,${data.data.plot}" alt="BER Heatmap" />`;
            }
        }
    } catch (e) { /* silent */ }
}


// ═══════════════════════════════════════════════════════════════════════════
//  Performance Profiler Widget
// ═══════════════════════════════════════════════════════════════════════════

function renderPerfWidget(metadata) {
    if (!metadata?.elapsed_seconds) return '';
    const elapsed = metadata.elapsed_seconds;
    const gpu = metadata.gpu_stats || {};

    let bars = `
        <div class="perf-bar-row">
            <span class="perf-bar-label">Total</span>
            <div class="perf-bar-track"><div class="perf-bar-value" style="width:100%;background:var(--accent-primary)"></div></div>
            <span class="perf-bar-time">${elapsed}s</span>
        </div>
    `;

    if (gpu.gpu_memory_allocated_mb) {
        bars += `
        <div class="perf-bar-row">
            <span class="perf-bar-label">GPU Mem</span>
            <div class="perf-bar-track"><div class="perf-bar-value" style="width:${Math.min(100, gpu.gpu_memory_allocated_mb/10)}%;background:var(--accent-secondary)"></div></div>
            <span class="perf-bar-time">${gpu.gpu_memory_allocated_mb}MB</span>
        </div>`;
    }

    if (metadata.engine === 'numpy_fallback') {
        bars += `<div style="font-size:11px;color:var(--accent-warm);margin-top:6px;">💡 Running on CPU fallback. Install Sionna for GPU acceleration.</div>`;
    }

    return `<div class="section-title" style="margin-top:16px;">⚡ Performance</div><div class="perf-widget">${bars}</div>`;
}


// ═══════════════════════════════════════════════════════════════════════════
//  Initialize Phase 3
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    loadUserPresets();
});
