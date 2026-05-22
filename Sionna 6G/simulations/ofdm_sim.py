"""
OFDM System Simulator
Full OFDM system simulation with configurable parameters,
pilot patterns, channel estimation, and equalization.

Now uses real Sionna OFDM stack (ResourceGrid, OFDMModulator, OFDMChannel,
LSChannelEstimator, LMMSEEqualizer/ZFEqualizer) when available, with NumPy fallback.
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64
import time

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Try importing Sionna OFDM components
try:
    import torch
    import sionna
    from sionna.phy.mapping import Mapper, Demapper, Constellation, BinarySource
    from sionna.phy.utils import hard_decisions, ebnodb2no
    from sionna.phy.ofdm import (
        ResourceGrid, ResourceGridMapper, ResourceGridDemapper,
        LSChannelEstimator, LMMSEEqualizer, ZFEqualizer, MFEqualizer,
    )
    from sionna.phy.channel import OFDMChannel, AWGN, RayleighBlockFading
    from sionna.phy.channel.tr38901 import TDL
    from sionna.phy.mimo import StreamManagement
    SIONNA_AVAILABLE = True
except ImportError:
    SIONNA_AVAILABLE = False


def run_ofdm_simulation(params):
    """
    Run a full OFDM system simulation.

    Parameters:
        params (dict):
            - num_subcarriers: int (64, 128, 256, 512, 1024, 2048)
            - cp_length: int (cyclic prefix length)
            - modulation: str ("qpsk", "16qam", "64qam")
            - num_symbols: int (OFDM symbols per frame)
            - channel_model: str ("awgn", "frequency_selective", "TDL-A")
            - snr_db: float
            - pilot_spacing: int (pilot every N subcarriers)
            - equalization: str ("zf", "mmse", "lmmse")
            - num_tx_antennas: int
            - num_rx_antennas: int

    Returns:
        dict with constellation, spectrum, equalizer comparison, metrics
    """
    num_sc = int(params.get("num_subcarriers", 256))
    cp_len = int(params.get("cp_length", 32))
    modulation = params.get("modulation", "qpsk")
    num_ofdm_symbols = int(params.get("num_symbols", 14))
    channel_model = params.get("channel_model", "frequency_selective")
    snr_db = float(params.get("snr_db", 15))
    pilot_spacing = int(params.get("pilot_spacing", 8))
    equalization = params.get("equalization", "mmse")
    num_tx = int(params.get("num_tx_antennas", 1))
    num_rx = int(params.get("num_rx_antennas", 1))

    mod_map = {"bpsk": 1, "qpsk": 2, "16qam": 4, "64qam": 6, "256qam": 8}
    bits_per_symbol = mod_map.get(modulation, 2)

    start_time = time.time()
    snr_linear = 10 ** (snr_db / 10.0)
    noise_var = 1.0 / snr_linear

    # Seed for reproducibility
    seed = params.get("seed", None)
    if seed is not None and seed != "" and seed != "auto":
        seed = int(seed)
        np.random.seed(seed)
        if TORCH_AVAILABLE:
            torch.manual_seed(seed)
    else:
        seed = int(np.random.randint(0, 2**31))
        np.random.seed(seed)
        if TORCH_AVAILABLE:
            torch.manual_seed(seed)

    # Try Sionna path first
    if SIONNA_AVAILABLE:
        try:
            result = _run_sionna_ofdm(
                num_sc, cp_len, modulation, bits_per_symbol,
                num_ofdm_symbols, channel_model, snr_db, noise_var,
                pilot_spacing, num_tx, num_rx, seed
            )
            result["metadata"]["elapsed_seconds"] = round(time.time() - start_time, 3)
            return result
        except Exception as e:
            print(f"[OFDM] Sionna path failed ({e}), falling back to NumPy")

    # NumPy fallback
    return _run_numpy_ofdm(
        num_sc, cp_len, modulation, bits_per_symbol,
        num_ofdm_symbols, channel_model, snr_db, noise_var,
        pilot_spacing, equalization, num_tx, num_rx, seed, start_time
    )


def _run_sionna_ofdm(num_sc, cp_len, modulation, bits_per_symbol,
                      num_ofdm_symbols, channel_model, snr_db, noise_var,
                      pilot_spacing, num_tx, num_rx, seed):
    """Run OFDM simulation using real Sionna OFDM stack."""

    # ── Build Sionna Resource Grid ──
    pilot_ofdm_indices = list(range(0, num_ofdm_symbols, max(1, pilot_spacing)))
    if len(pilot_ofdm_indices) < 1:
        pilot_ofdm_indices = [0]
    # Clamp to at most half the OFDM symbols for pilots
    if len(pilot_ofdm_indices) > num_ofdm_symbols // 2:
        pilot_ofdm_indices = pilot_ofdm_indices[:max(1, num_ofdm_symbols // 2)]

    rg = ResourceGrid(
        num_ofdm_symbols=num_ofdm_symbols,
        fft_size=num_sc,
        subcarrier_spacing=15e3,
        num_tx=1,
        num_streams_per_tx=1,
        cyclic_prefix_length=cp_len,
        pilot_pattern="kronecker",
        pilot_ofdm_symbol_indices=pilot_ofdm_indices
    )

    # ── Build Sionna components ──
    constellation = Constellation("qam", num_bits_per_symbol=bits_per_symbol)
    mapper = Mapper(constellation=constellation)
    demapper = Demapper("app", constellation=constellation)
    source = BinarySource()
    rg_mapper = ResourceGridMapper(rg)
    rg_demapper = ResourceGridDemapper(rg)

    # Channel model
    is_tdl = channel_model.startswith("TDL-")
    if is_tdl:
        model_letter = channel_model.replace("TDL-", "")
        if model_letter not in ('A', 'B', 'C', 'D', 'E'):
            model_letter = 'A'
        ch_model = TDL(
            model=model_letter,
            delay_spread=100e-9,
            carrier_frequency=3.5e9,
            min_speed=0.0, max_speed=0.0,
            num_rx_ant=1, num_tx_ant=1
        )
    elif channel_model == "frequency_selective":
        ch_model = TDL(
            model="A",
            delay_spread=100e-9,
            carrier_frequency=3.5e9,
            min_speed=0.0, max_speed=0.0,
            num_rx_ant=1, num_tx_ant=1
        )
    else:
        # AWGN — use RayleighBlockFading with identity-like behaviour
        ch_model = RayleighBlockFading(
            num_rx=1, num_rx_ant=1,
            num_tx=1, num_tx_ant=1
        )

    ofdm_channel = OFDMChannel(ch_model, rg, return_channel=True)

    # Stream management for equalizers
    rx_tx_association = np.array([[1]])
    sm = StreamManagement(rx_tx_association, num_streams_per_tx=1)

    # Build equalizers
    ls_est = LSChannelEstimator(rg, interpolation_type="lin")
    lmmse_eq = LMMSEEqualizer(rg, sm)
    zf_eq = ZFEqualizer(rg, sm)
    mf_eq = MFEqualizer(rg, sm)

    # Noise variance
    no = ebnodb2no(snr_db, num_bits_per_symbol=bits_per_symbol, coderate=1.0)
    no_tensor = torch.tensor(no, dtype=torch.float32)

    # ── TX Pipeline ──
    batch_size = 1
    num_data_bits = rg.num_data_symbols * bits_per_symbol
    bits = source([batch_size, 1, 1, num_data_bits])
    x = mapper(bits)
    x_rg = rg_mapper(x)

    # ── Channel ──
    y, h_freq = ofdm_channel(x_rg, no)
    # y: [batch, num_rx, num_rx_ant, num_ofdm_symbols, fft_size]
    # h_freq: [batch, num_rx, num_rx_ant, num_tx, num_tx_ant, num_ofdm_symbols, fft_size]

    # ── RX: Channel Estimation ──
    h_hat, err_var = ls_est(y, no_tensor)

    # ── Equalization with each equalizer ──
    ber_by_eq = {}
    all_rx_eq_np = {}
    all_tx_np = x.detach().cpu().numpy().flatten()

    eq_configs = [
        ("zf", zf_eq),
        ("mmse", lmmse_eq),
        ("lmmse", mf_eq),
    ]

    for eq_name, equalizer in eq_configs:
        try:
            x_hat, no_eff = equalizer(y, h_hat, err_var, no_tensor)
            x_hat_flat = x_hat.detach().cpu().numpy().flatten()
            all_rx_eq_np[eq_name] = x_hat_flat

            # Compute BER via hard decisions
            llr_eq = demapper(x_hat, no_tensor)
            bits_hat = hard_decisions(llr_eq)
            min_len = min(bits_hat.shape[-1], bits.shape[-1])
            errors = torch.sum(
                bits_hat[..., :min_len] != bits[..., :min_len]
            ).item()
            ber = errors / max(min_len, 1)
            ber_by_eq[eq_name] = round(float(ber), 6)
        except Exception as e:
            # If equalizer fails, mark as N/A
            all_rx_eq_np[eq_name] = all_tx_np
            ber_by_eq[eq_name] = -1.0
            print(f"[OFDM] Equalizer '{eq_name}' failed: {e}")

    # ── Extract numpy arrays for plotting ──
    # True channel and estimated channel (for comparison plot)
    H_true_np = h_freq[0, 0, 0, 0, 0, 0, :].detach().cpu().numpy()  # [fft_size]
    H_est_np = h_hat[0, 0, 0, 0, 0, 0, :].detach().cpu().numpy()    # [fft_size]
    subcarriers = np.arange(num_sc)

    # Channel frequency response
    H_mag_np = torch.abs(h_freq[0, 0, 0, 0, 0, 0, :]).detach().cpu().numpy()

    # ── Generate plots ──
    spectrum_plot = _plot_ofdm_spectrum(H_true_np, num_sc, channel_model)
    eq_comparison_plot = _plot_equalizer_comparison(
        all_tx_np[:2000], all_rx_eq_np, modulation, snr_db, 2000
    )

    # Resource grid info
    pilot_positions = list(range(0, num_sc, max(1, pilot_spacing)))
    data_positions = [i for i in range(num_sc) if i not in pilot_positions]
    resource_grid_plot = _plot_resource_grid(
        num_sc, num_ofdm_symbols, pilot_positions, data_positions
    )
    channel_est_plot = _plot_channel_estimation(H_true_np, subcarriers, H_est_np)

    # Metrics
    num_pilots = rg.num_pilot_symbols
    num_data = rg.num_data_symbols

    return {
        "spectrum_plot": spectrum_plot,
        "eq_comparison_plot": eq_comparison_plot,
        "resource_grid_plot": resource_grid_plot,
        "channel_est_plot": channel_est_plot,
        "ber_by_equalizer": ber_by_eq,
        "metrics": {
            "num_subcarriers": num_sc,
            "num_data_subcarriers": int(num_data),
            "num_pilots": int(num_pilots),
            "pilot_overhead_percent": round(float(num_pilots) / max(num_sc * num_ofdm_symbols, 1) * 100, 1),
            "cp_overhead_percent": round(cp_len / (num_sc + cp_len) * 100, 1),
            "spectral_efficiency": round(bits_per_symbol * num_data / max(num_sc * num_ofdm_symbols, 1) * (num_sc / (num_sc + cp_len)), 3),
            "best_equalizer": min(ber_by_eq, key=ber_by_eq.get) if ber_by_eq else "N/A"
        },
        "metadata": {
            "num_subcarriers": num_sc,
            "cp_length": cp_len,
            "modulation": modulation,
            "num_symbols": num_ofdm_symbols,
            "channel_model": channel_model,
            "snr_db": snr_db,
            "equalization": "all",
            "num_tx_antennas": num_tx,
            "num_rx_antennas": num_rx,
            "elapsed_seconds": 0,
            "seed": seed,
            "engine": "sionna"
        }
    }


def _run_numpy_ofdm(num_sc, cp_len, modulation, bits_per_symbol,
                     num_ofdm_symbols, channel_model, snr_db, noise_var,
                     pilot_spacing, equalization, num_tx, num_rx, seed, start_time):
    """NumPy fallback OFDM simulation."""

    # ---- Generate QAM constellation ----
    M = 2 ** bits_per_symbol
    sqrt_M = int(np.ceil(np.sqrt(M)))
    real_vals = np.arange(-(sqrt_M - 1), sqrt_M, 2)
    imag_vals = np.arange(-(sqrt_M - 1), sqrt_M, 2)
    qam_points = []
    for r in real_vals:
        for i in imag_vals:
            qam_points.append(complex(r, i))
    qam_points = np.array(qam_points[:M])
    avg_power = np.mean(np.abs(qam_points) ** 2)
    qam_points /= np.sqrt(avg_power)

    # ---- Create resource grid ----
    pilot_positions = list(range(0, num_sc, pilot_spacing))
    data_positions = [i for i in range(num_sc) if i not in pilot_positions]
    num_pilots = len(pilot_positions)
    num_data = len(data_positions)

    # ---- Generate channel ----
    if channel_model == "awgn":
        H = np.ones(num_sc, dtype=complex)
    elif channel_model == "frequency_selective":
        num_taps = min(cp_len, 16)
        h_time = (np.random.randn(num_taps) + 1j * np.random.randn(num_taps)) / np.sqrt(2 * num_taps)
        decay = np.exp(-np.arange(num_taps) / (num_taps / 3))
        h_time *= decay
        H = np.fft.fft(h_time, num_sc)
    else:  # TDL model
        from simulations.channel_sim import TDL_MODELS
        tdl = TDL_MODELS.get(channel_model, TDL_MODELS["TDL-A"])
        delays_ns = np.array(tdl["delays_ns"], dtype=float)
        powers_db = np.array(tdl["powers_db"], dtype=float)
        powers_lin = 10 ** (powers_db / 10.0)
        powers_lin /= np.sum(powers_lin)

        sc_spacing_hz = 15e3
        freq_axis = np.arange(num_sc) * sc_spacing_hz
        H = np.zeros(num_sc, dtype=complex)
        for delay_ns, power in zip(delays_ns, powers_lin):
            delay_s = delay_ns * 1e-9
            amp = np.sqrt(power) * (np.random.randn() + 1j * np.random.randn()) / np.sqrt(2)
            H += amp * np.exp(-1j * 2 * np.pi * freq_axis * delay_s)

    # ---- Simulate OFDM frames ----
    all_tx_data = []
    all_rx_data = []
    all_rx_eq = {"zf": [], "mmse": [], "lmmse": []}
    ber_by_eq = {}

    for sym_idx in range(num_ofdm_symbols):
        tx_indices = np.random.randint(0, M, num_data)
        tx_data = qam_points[tx_indices]

        tx_ofdm = np.zeros(num_sc, dtype=complex)
        pilot_val = (1 + 1j) / np.sqrt(2)
        for p in pilot_positions:
            tx_ofdm[p] = pilot_val
        for i, pos in enumerate(data_positions):
            tx_ofdm[pos] = tx_data[i]

        all_tx_data.extend(tx_data)

        rx_ofdm = H * tx_ofdm
        noise = np.sqrt(noise_var / 2) * (np.random.randn(num_sc) + 1j * np.random.randn(num_sc))
        rx_ofdm += noise

        # Channel estimation from pilots
        H_pilots = np.zeros(num_pilots, dtype=complex)
        for i, p in enumerate(pilot_positions):
            H_pilots[i] = rx_ofdm[p] / pilot_val

        H_est = np.interp(
            np.arange(num_sc), pilot_positions, np.real(H_pilots)
        ) + 1j * np.interp(
            np.arange(num_sc), pilot_positions, np.imag(H_pilots)
        )

        rx_data = np.array([rx_ofdm[pos] for pos in data_positions])
        H_data = np.array([H_est[pos] for pos in data_positions])

        zf_eq = rx_data / (H_data + 1e-10)
        all_rx_eq["zf"].extend(zf_eq)

        mmse_eq = (np.conj(H_data) * rx_data) / (np.abs(H_data) ** 2 + noise_var)
        all_rx_eq["mmse"].extend(mmse_eq)

        sigma2_h = np.var(H_data)
        lmmse_eq = (np.conj(H_data) * rx_data) / (np.abs(H_data) ** 2 + noise_var / (sigma2_h + 1e-10))
        all_rx_eq["lmmse"].extend(lmmse_eq)

    all_tx_data = np.array(all_tx_data)

    # Compute BER for each equalizer
    for eq_name, eq_data in all_rx_eq.items():
        eq_data = np.array(eq_data)
        decisions = np.array([qam_points[np.argmin(np.abs(qam_points - s))] for s in eq_data[:min(len(eq_data), 5000)]])
        ref = all_tx_data[:len(decisions)]
        errors = np.sum(decisions != ref)
        ber_by_eq[eq_name] = round(float(errors / max(len(decisions), 1)), 6)

    # Generate plots
    spectrum_plot = _plot_ofdm_spectrum(H, num_sc, channel_model)
    eq_comparison_plot = _plot_equalizer_comparison(
        all_tx_data[:2000], all_rx_eq, modulation, snr_db, 2000
    )
    resource_grid_plot = _plot_resource_grid(
        num_sc, num_ofdm_symbols, pilot_positions, data_positions
    )
    channel_est_plot = _plot_channel_estimation(H, np.arange(num_sc), H_est)

    elapsed = time.time() - start_time

    return {
        "spectrum_plot": spectrum_plot,
        "eq_comparison_plot": eq_comparison_plot,
        "resource_grid_plot": resource_grid_plot,
        "channel_est_plot": channel_est_plot,
        "ber_by_equalizer": ber_by_eq,
        "metrics": {
            "num_subcarriers": num_sc,
            "num_data_subcarriers": num_data,
            "num_pilots": num_pilots,
            "pilot_overhead_percent": round(num_pilots / num_sc * 100, 1),
            "cp_overhead_percent": round(cp_len / (num_sc + cp_len) * 100, 1),
            "spectral_efficiency": round(bits_per_symbol * num_data / num_sc * (num_sc / (num_sc + cp_len)), 3),
            "best_equalizer": min(ber_by_eq, key=ber_by_eq.get) if ber_by_eq else "N/A"
        },
        "metadata": {
            "num_subcarriers": num_sc,
            "cp_length": cp_len,
            "modulation": modulation,
            "num_symbols": num_ofdm_symbols,
            "channel_model": channel_model,
            "snr_db": snr_db,
            "equalization": equalization,
            "num_tx_antennas": num_tx,
            "num_rx_antennas": num_rx,
            "elapsed_seconds": round(elapsed, 3),
            "seed": seed,
            "engine": "numpy_fallback"
        }
    }


def _plot_ofdm_spectrum(H, num_sc, channel_model):
    """Plot the OFDM channel frequency response."""
    fig, ax = plt.subplots(figsize=(10, 4), facecolor='#0a0a1a')
    ax.set_facecolor('#0a0a1a')

    freq_axis = np.arange(num_sc)
    magnitude_db = 20 * np.log10(np.abs(H) + 1e-10)

    ax.plot(freq_axis, magnitude_db, color='#76B900', linewidth=1.2, alpha=0.9)
    ax.fill_between(freq_axis, magnitude_db, min(magnitude_db) - 3, alpha=0.08, color='#76B900')

    ax.set_xlabel('Subcarrier Index', color='#aaaacc', fontsize=11)
    ax.set_ylabel('|H(f)| (dB)', color='#aaaacc', fontsize=11)
    ax.set_title(f'OFDM Channel — {channel_model}', color='#ffffff', fontsize=13, fontweight='bold')
    ax.grid(True, alpha=0.12, color='#444466')
    ax.tick_params(colors='#666688')
    for spine in ax.spines.values():
        spine.set_color('#333355')
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def _plot_equalizer_comparison(tx_data, rx_eq_data, modulation, snr_db, max_pts):
    """Plot constellation comparison across equalizers."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor='#0a0a1a')

    eq_names = ["zf", "mmse", "lmmse"]
    eq_labels = ["Zero-Forcing", "MMSE", "LMMSE"]
    colors = ['#00d4ff', '#76B900', '#ff6b35']

    for ax, name, label, color in zip(axes, eq_names, eq_labels, colors):
        ax.set_facecolor('#0a0a1a')
        data = np.array(rx_eq_data[name][:max_pts]) if name in rx_eq_data else np.array([])

        if len(data) > 0:
            ax.scatter(np.real(data), np.imag(data), c=color, alpha=0.12, s=6, marker='.')

        # TX reference
        tx_unique = np.unique(np.round(tx_data, 6))
        ax.scatter(np.real(tx_unique), np.imag(tx_unique), c='#ffffff', s=40, marker='x', linewidths=1.5, zorder=5)

        ax.set_title(label, color=color, fontsize=12, fontweight='bold')
        ax.set_xlabel('I', color='#666688', fontsize=9)
        ax.set_ylabel('Q', color='#666688', fontsize=9)
        ax.grid(True, alpha=0.1, color='#444466')
        ax.tick_params(colors='#555577', labelsize=8)
        ax.axhline(0, color='#333355', linewidth=0.5)
        ax.axvline(0, color='#333355', linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_color('#333355')

    fig.suptitle(f'{modulation.upper()} | SNR={snr_db}dB — Equalizer Comparison',
                 color='#ffffff', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def _plot_resource_grid(num_sc, num_symbols, pilot_pos, data_pos):
    """Plot the OFDM resource grid visualization."""
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#0a0a1a')
    ax.set_facecolor('#0a0a1a')

    display_sc = min(num_sc, 64)
    display_sym = min(num_symbols, 14)

    grid = np.zeros((display_sc, display_sym))
    pilot_set = set(p for p in pilot_pos if p < display_sc)

    for sc in range(display_sc):
        for sym in range(display_sym):
            if sc in pilot_set:
                grid[sc, sym] = 2  # Pilot
            else:
                grid[sc, sym] = 1  # Data

    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(['#0a0a1a', '#1a3a5c', '#ff6b35'])

    ax.imshow(grid, aspect='auto', cmap=cmap, interpolation='nearest', origin='lower')
    ax.set_xlabel('OFDM Symbol', color='#aaaacc', fontsize=11)
    ax.set_ylabel('Subcarrier', color='#aaaacc', fontsize=11)
    ax.set_title('Resource Grid (Blue=Data, Orange=Pilot)',
                 color='#ffffff', fontsize=13, fontweight='bold')
    ax.tick_params(colors='#666688')
    for spine in ax.spines.values():
        spine.set_color('#333355')

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def _plot_channel_estimation(H_true, subcarriers, H_est):
    """Plot true vs estimated channel."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), facecolor='#0a0a1a')

    for ax in [ax1, ax2]:
        ax.set_facecolor('#0a0a1a')

    # Magnitude
    ax1.plot(subcarriers, 20 * np.log10(np.abs(H_true) + 1e-10),
             color='#76B900', linewidth=1.5, alpha=0.8, label='True H')
    ax1.plot(subcarriers, 20 * np.log10(np.abs(H_est) + 1e-10),
             color='#00d4ff', linewidth=1, alpha=0.7, linestyle='--', label='Estimated H')
    ax1.set_ylabel('|H| (dB)', color='#aaaacc', fontsize=11)
    ax1.set_title('Channel Estimation — Magnitude', color='#ffffff', fontsize=13, fontweight='bold')
    ax1.legend(facecolor='#1a1a2e', edgecolor='#333355', labelcolor='#aaaacc')
    ax1.grid(True, alpha=0.12, color='#444466')
    ax1.tick_params(colors='#666688')

    # Phase
    ax2.plot(subcarriers, np.angle(H_true), color='#76B900', linewidth=1.5, alpha=0.8, label='True Phase')
    ax2.plot(subcarriers, np.angle(H_est), color='#00d4ff', linewidth=1, alpha=0.7, linestyle='--', label='Est. Phase')
    ax2.set_xlabel('Subcarrier', color='#aaaacc', fontsize=11)
    ax2.set_ylabel('Phase (rad)', color='#aaaacc', fontsize=11)
    ax2.set_title('Channel Estimation — Phase', color='#ffffff', fontsize=13, fontweight='bold')
    ax2.legend(facecolor='#1a1a2e', edgecolor='#333355', labelcolor='#aaaacc')
    ax2.grid(True, alpha=0.12, color='#444466')
    ax2.tick_params(colors='#666688')

    for ax in [ax1, ax2]:
        for spine in ax.spines.values():
            spine.set_color('#333355')

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')
