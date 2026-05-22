"""
Channel Response Simulator
Generates channel impulse response, frequency response, and power delay profiles
for various 3GPP channel models.

Now uses real Sionna TDL/CDL models from sionna.phy.channel.tr38901 when available,
with NumPy fallback for environments without Sionna.
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

# Try importing Sionna channel models
try:
    import torch
    import sionna
    from sionna.phy.channel.tr38901 import TDL, CDL
    from sionna.phy.channel import GenerateOFDMChannel
    from sionna.phy.ofdm import ResourceGrid
    SIONNA_AVAILABLE = True
except ImportError:
    SIONNA_AVAILABLE = False


# 3GPP TDL channel model delay profiles (for NumPy fallback and UI reference)
TDL_MODELS = {
    "TDL-A": {
        "description": "NLOS - Urban Micro / Macro",
        "delays_ns": [0, 30, 70, 90, 110, 190, 410, 500, 600, 730, 860, 1070, 1280, 1460, 1620, 1770, 2100, 2300, 2500, 2750, 3000, 3200, 3500],
        "powers_db": [-13.4, 0, -2.2, -4, -6, -8.2, -9.9, -10.5, -7.5, -15.9, -6.6, -16.7, -12.4, -15.2, -10.8, -11.3, -12.7, -16.2, -18.3, -18.9, -16.6, -19.9, -29.7]
    },
    "TDL-B": {
        "description": "NLOS - Urban Micro",
        "delays_ns": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 500, 700, 1000, 1500, 2000, 2500, 3000],
        "powers_db": [0, -2.2, -4, -3.2, -9.8, -1.2, -3.4, -5.2, -7.6, -3.0, -8.9, -9.0, -4.8, -7.3, -7.1, -13.3, -12.0, -15.8, -18.1, -22.0]
    },
    "TDL-C": {
        "description": "NLOS - Urban Macro",
        "delays_ns": [0, 20, 45, 65, 85, 105, 155, 230, 360, 475, 630, 830, 1020, 1210, 1510, 1810, 2110, 2510, 2910, 3310, 3710, 4110, 4510, 4910],
        "powers_db": [-4.4, -1.2, -3.5, -5.2, -2.5, 0, -2.2, -3.9, -7.4, -7.1, -10.7, -11.3, -5.7, -14.1, -9.3, -12.7, -18.3, -14.1, -14.7, -20.7, -19.2, -22.1, -24.6, -27.0]
    },
    "TDL-D": {
        "description": "LOS - Rural Macro",
        "delays_ns": [0, 10, 30, 50, 65, 75, 95, 145, 210, 290, 450, 650, 850, 1050],
        "powers_db": [-0.2, -13.5, -18.8, -21, -22.8, -17.9, -20.1, -21.9, -22.2, -18.5, -24.0, -25.0, -27.0, -30.0]
    },
    "TDL-E": {
        "description": "LOS - Indoor Office",
        "delays_ns": [0, 10, 20, 30, 50, 80, 110, 140, 180, 230, 280, 350, 450, 550],
        "powers_db": [-0.03, -22.03, -15.8, -18.1, -19.8, -22.9, -22.4, -18.6, -20.8, -22.6, -25.0, -26.5, -28.3, -30.0]
    }
}

# CDL model descriptions (for UI reference — actual models are in Sionna)
CDL_MODELS = {
    "CDL-A": {"description": "NLOS - Urban Micro (Clustered)"},
    "CDL-B": {"description": "NLOS - Urban Micro (Clustered)"},
    "CDL-C": {"description": "NLOS - Urban Macro (Clustered)"},
    "CDL-D": {"description": "LOS - Urban Macro (Clustered)"},
    "CDL-E": {"description": "LOS - Rural (Clustered)"},
}


def run_channel_simulation(params):
    """
    Simulate channel response for a given model.

    Parameters:
        params (dict):
            - model: str ("TDL-A".."TDL-E", "CDL-A".."CDL-E")
            - delay_spread_ns: float (desired RMS delay spread scaling)
            - num_subcarriers: int
            - subcarrier_spacing_khz: float
            - num_realizations: int

    Returns:
        dict with time/frequency domain data and plots
    """
    model = params.get("model", "TDL-A")
    delay_spread_ns = float(params.get("delay_spread_ns", 100))
    num_subcarriers = int(params.get("num_subcarriers", 256))
    subcarrier_spacing_khz = float(params.get("subcarrier_spacing_khz", 15))
    num_realizations = int(params.get("num_realizations", 100))

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

    start_time = time.time()

    is_cdl = model.startswith("CDL-")
    is_tdl = model.startswith("TDL-")
    model_letter = model.split("-")[-1] if "-" in model else "A"

    # Try Sionna path first
    if SIONNA_AVAILABLE and (is_tdl or is_cdl):
        try:
            result = _run_sionna_channel(
                model, model_letter, is_cdl,
                delay_spread_ns, num_subcarriers,
                subcarrier_spacing_khz, num_realizations, seed
            )
            result["metadata"]["elapsed_seconds"] = round(time.time() - start_time, 3)
            result["metadata"]["engine"] = "sionna"
            return result
        except Exception as e:
            print(f"[Channel] Sionna path failed ({e}), falling back to NumPy")

    # NumPy fallback path
    return _run_numpy_channel(
        model, delay_spread_ns, num_subcarriers,
        subcarrier_spacing_khz, num_realizations, seed, start_time
    )


def _run_sionna_channel(model, model_letter, is_cdl, delay_spread_ns,
                        num_subcarriers, subcarrier_spacing_khz,
                        num_realizations, seed):
    """Run channel simulation using real Sionna TDL/CDL models."""
    delay_spread_s = delay_spread_ns * 1e-9
    carrier_frequency = 3.5e9
    sc_spacing_hz = subcarrier_spacing_khz * 1e3

    # Create Sionna channel model
    if is_cdl:
        channel_model = CDL(
            model=model_letter,
            delay_spread=delay_spread_s,
            carrier_frequency=carrier_frequency,
            min_speed=0.0, max_speed=0.0,
            num_rx_ant=1, num_tx_ant=1
        )
        description = CDL_MODELS.get(model, {}).get("description", f"CDL-{model_letter}")
    else:
        channel_model = TDL(
            model=model_letter,
            delay_spread=delay_spread_s,
            carrier_frequency=carrier_frequency,
            min_speed=0.0, max_speed=0.0,
            num_rx_ant=1, num_tx_ant=1
        )
        description = TDL_MODELS.get(model, {}).get("description", f"TDL-{model_letter}")

    # Generate CIR: get path coefficients and delays
    sampling_freq = sc_spacing_hz * num_subcarriers
    h, tau = channel_model(
        batch_size=num_realizations,
        num_time_steps=1,
        sampling_frequency=sampling_freq
    )
    # h: [batch, 1, 1, 1, 1, num_paths, 1]
    # tau: [batch, 1, 1, num_paths]

    # Extract delays (average over batch — should be identical)
    delays_s = tau[0, 0, 0, :].detach().cpu().numpy()
    delays_ns = delays_s * 1e9

    # Extract average path powers
    # h shape: [batch, num_rx=1, num_rx_ant=1, num_tx=1, num_tx_ant=1, num_paths, num_time_steps=1]
    h_power = torch.mean(torch.abs(h) ** 2, dim=(0, 1, 2, 3, 4, 6))  # [num_paths]
    powers_linear = h_power.detach().cpu().numpy()
    powers_db = 10 * np.log10(powers_linear + 1e-30)

    # Generate frequency response using Sionna's OFDM channel
    cp_len = max(1, num_subcarriers // 8)
    rg = ResourceGrid(
        num_ofdm_symbols=14,
        fft_size=num_subcarriers,
        subcarrier_spacing=sc_spacing_hz,
        num_tx=1,
        num_streams_per_tx=1,
        cyclic_prefix_length=cp_len
    )

    gen_ofdm = GenerateOFDMChannel(channel_model, rg)
    h_freq = gen_ofdm(batch_size=num_realizations)
    # h_freq: [batch, num_rx, num_rx_ant, num_tx, num_tx_ant, num_ofdm_symbols, fft_size]

    # Average power over batch, antennas, OFDM symbols
    H_power_avg = torch.mean(
        torch.abs(h_freq) ** 2, dim=(0, 1, 2, 3, 4, 5)
    ).detach().cpu().numpy()
    freq_response_db = 10 * np.log10(H_power_avg + 1e-30)

    # Compute channel statistics from Sionna model
    if hasattr(channel_model, 'delays') and hasattr(channel_model, 'mean_powers'):
        model_delays = channel_model.delays.detach().cpu().numpy() * 1e9  # ns
        model_powers = channel_model.mean_powers.detach().cpu().numpy()
    else:
        model_delays = delays_ns
        model_powers = powers_linear

    # Normalize powers for statistics
    total_power = np.sum(model_powers)
    if total_power > 0:
        p_norm = model_powers / total_power
    else:
        p_norm = model_powers

    mean_delay = np.sum(p_norm * model_delays)
    rms_delay = np.sqrt(np.sum(p_norm * model_delays ** 2) - mean_delay ** 2)
    coherence_bw = 1 / (5 * rms_delay * 1e-9 + 1e-12) / 1e6  # MHz

    # Generate plots
    bandwidth_hz = num_subcarriers * sc_spacing_hz
    freq_axis_mhz = np.linspace(-bandwidth_hz / 2, bandwidth_hz / 2, num_subcarriers) / 1e6

    cir_plot = _plot_cir(delays_ns, powers_db, model, description)
    freq_plot = _plot_frequency_response(freq_axis_mhz, freq_response_db, model, bandwidth_hz / 1e6)
    pdp_plot = _plot_power_delay_profile(delays_ns, powers_linear, model)

    return {
        "cir_plot": cir_plot,
        "freq_plot": freq_plot,
        "pdp_plot": pdp_plot,
        "delays_ns": delays_ns.tolist(),
        "powers_db": powers_db.tolist(),
        "freq_response_db": freq_response_db.tolist(),
        "statistics": {
            "rms_delay_spread_ns": round(float(rms_delay), 2),
            "coherence_bandwidth_mhz": round(float(coherence_bw), 2),
            "max_delay_ns": round(float(max(delays_ns)), 2),
            "num_taps": len(delays_ns),
            "model": model,
            "description": description
        },
        "metadata": {
            "model": model,
            "delay_spread_ns": delay_spread_ns,
            "num_subcarriers": num_subcarriers,
            "subcarrier_spacing_khz": subcarrier_spacing_khz,
            "num_realizations": num_realizations,
            "elapsed_seconds": 0,
            "seed": seed,
            "engine": "sionna"
        }
    }


def _run_numpy_channel(model, delay_spread_ns, num_subcarriers,
                       subcarrier_spacing_khz, num_realizations, seed, start_time):
    """NumPy fallback for channel simulation."""
    tdl = TDL_MODELS.get(model, TDL_MODELS["TDL-A"])
    delays_ns = np.array(tdl["delays_ns"], dtype=float)
    powers_db = np.array(tdl["powers_db"], dtype=float)
    description = tdl.get("description", model)

    # Scale delays
    if max(delays_ns) > 0:
        scale = delay_spread_ns / (np.sqrt(np.sum(10 ** (powers_db / 10) * delays_ns ** 2) /
                                           np.sum(10 ** (powers_db / 10)) + 1e-12) + 1e-12)
        delays_scaled_ns = delays_ns * scale
    else:
        delays_scaled_ns = delays_ns

    # Convert powers to linear
    powers_linear = 10 ** (powers_db / 10.0)
    powers_linear = powers_linear / np.sum(powers_linear)  # Normalize

    # Frequency domain
    sc_spacing_hz = subcarrier_spacing_khz * 1e3
    bandwidth_hz = num_subcarriers * sc_spacing_hz
    freq_axis = np.linspace(-bandwidth_hz / 2, bandwidth_hz / 2, num_subcarriers)

    # Average frequency response over realizations
    H_avg = np.zeros(num_subcarriers, dtype=complex)
    H_power_avg = np.zeros(num_subcarriers)

    for _ in range(num_realizations):
        H = np.zeros(num_subcarriers, dtype=complex)
        for delay_ns, power in zip(delays_scaled_ns, powers_linear):
            delay_s = delay_ns * 1e-9
            phase = np.exp(-1j * 2 * np.pi * freq_axis * delay_s)
            amp = np.sqrt(power) * (np.random.randn() + 1j * np.random.randn()) / np.sqrt(2)
            H += amp * phase
        H_avg += H
        H_power_avg += np.abs(H) ** 2

    H_avg /= num_realizations
    H_power_avg /= num_realizations

    freq_response_db = 10 * np.log10(H_power_avg + 1e-30)

    # Generate plots
    cir_plot = _plot_cir(delays_scaled_ns, powers_db, model, description)
    freq_plot = _plot_frequency_response(freq_axis / 1e6, freq_response_db, model, bandwidth_hz / 1e6)
    pdp_plot = _plot_power_delay_profile(delays_scaled_ns, powers_linear, model)

    elapsed = time.time() - start_time

    # Compute channel statistics
    rms_delay = np.sqrt(
        np.sum(powers_linear * delays_scaled_ns ** 2) / np.sum(powers_linear) -
        (np.sum(powers_linear * delays_scaled_ns) / np.sum(powers_linear)) ** 2
    )
    coherence_bw = 1 / (5 * rms_delay * 1e-9 + 1e-12) / 1e6  # MHz

    return {
        "cir_plot": cir_plot,
        "freq_plot": freq_plot,
        "pdp_plot": pdp_plot,
        "delays_ns": delays_scaled_ns.tolist(),
        "powers_db": powers_db.tolist(),
        "freq_response_db": freq_response_db.tolist(),
        "statistics": {
            "rms_delay_spread_ns": round(float(rms_delay), 2),
            "coherence_bandwidth_mhz": round(float(coherence_bw), 2),
            "max_delay_ns": round(float(max(delays_scaled_ns)), 2),
            "num_taps": len(delays_ns),
            "model": model,
            "description": description
        },
        "metadata": {
            "model": model,
            "delay_spread_ns": delay_spread_ns,
            "num_subcarriers": num_subcarriers,
            "subcarrier_spacing_khz": subcarrier_spacing_khz,
            "num_realizations": num_realizations,
            "elapsed_seconds": round(elapsed, 3),
            "seed": seed,
            "engine": "numpy_fallback"
        }
    }


def _plot_cir(delays_ns, powers_db, model, description):
    """Plot channel impulse response."""
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#0a0a1a')
    ax.set_facecolor('#0a0a1a')

    colors = plt.cm.plasma(np.linspace(0.2, 0.9, len(delays_ns)))
    markerline, stemlines, baseline = ax.stem(delays_ns, powers_db, linefmt='-', markerfmt='o', basefmt=' ')
    plt.setp(stemlines, color='#00d4ff', linewidth=2, alpha=0.7)
    plt.setp(markerline, color='#ff6b35', markersize=8, zorder=5)

    ax.set_xlabel('Delay (ns)', color='#aaaacc', fontsize=12)
    ax.set_ylabel('Power (dB)', color='#aaaacc', fontsize=12)
    ax.set_title(f'Channel Impulse Response — {model} ({description})',
                 color='#ffffff', fontsize=14, fontweight='bold', pad=15)
    ax.grid(True, alpha=0.15, color='#444466')
    ax.tick_params(colors='#666688')
    for spine in ax.spines.values():
        spine.set_color('#333355')

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def _plot_frequency_response(freq_mhz, response_db, model, bw_mhz):
    """Plot channel frequency response."""
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#0a0a1a')
    ax.set_facecolor('#0a0a1a')

    ax.plot(freq_mhz, response_db, color='#76B900', linewidth=1.5, alpha=0.9)
    ax.fill_between(freq_mhz, response_db, min(response_db) - 5, alpha=0.1, color='#76B900')

    ax.set_xlabel('Frequency (MHz)', color='#aaaacc', fontsize=12)
    ax.set_ylabel('|H(f)|² (dB)', color='#aaaacc', fontsize=12)
    ax.set_title(f'Frequency Response — {model} | BW={bw_mhz:.1f} MHz',
                 color='#ffffff', fontsize=14, fontweight='bold', pad=15)
    ax.grid(True, alpha=0.15, color='#444466')
    ax.tick_params(colors='#666688')
    for spine in ax.spines.values():
        spine.set_color('#333355')

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def _plot_power_delay_profile(delays_ns, powers_linear, model):
    """Plot power delay profile."""
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#0a0a1a')
    ax.set_facecolor('#0a0a1a')

    powers_norm = powers_linear / max(powers_linear)
    ax.bar(delays_ns, powers_norm, width=max(delays_ns) * 0.015 + 1,
           color='#00d4ff', alpha=0.7, edgecolor='#00a0cc')

    ax.set_xlabel('Delay (ns)', color='#aaaacc', fontsize=12)
    ax.set_ylabel('Normalized Power', color='#aaaacc', fontsize=12)
    ax.set_title(f'Power Delay Profile — {model}',
                 color='#ffffff', fontsize=14, fontweight='bold', pad=15)
    ax.grid(True, alpha=0.15, color='#444466', axis='y')
    ax.tick_params(colors='#666688')
    for spine in ax.spines.values():
        spine.set_color('#333355')

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')
