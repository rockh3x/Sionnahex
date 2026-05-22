"""
Constellation Diagram Generator
Generates TX/RX constellation scatter plots with EVM computation.
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
    import sionna
    from sionna.phy.mapping import Mapper, Constellation, BinarySource
    from sionna.phy.channel import AWGN
    SIONNA_AVAILABLE = True
except ImportError:
    SIONNA_AVAILABLE = False


def run_constellation_simulation(params):
    """
    Generate constellation diagrams showing TX and RX points.

    Parameters:
        params (dict):
            - modulation: str ("qpsk", "16qam", "64qam", "256qam")
            - snr_db: float
            - channel: str ("awgn", "rayleigh", "rician")
            - num_symbols: int
            - seed: int or None (for reproducibility)

    Returns:
        dict with plot (base64 image), evm, metrics
    """
    modulation = params.get("modulation", "qpsk")
    snr_db = float(params.get("snr_db", 15))
    channel = params.get("channel", "awgn")
    num_symbols = int(params.get("num_symbols", 2000))

    # Seed for reproducibility
    seed = params.get("seed", None)
    if seed is not None and seed != "" and seed != "auto":
        seed = int(seed)
        np.random.seed(seed)
    else:
        seed = int(np.random.randint(0, 2**31))
        np.random.seed(seed)

    mod_map = {"bpsk": 1, "qpsk": 2, "16qam": 4, "64qam": 6, "256qam": 8}
    bits_per_symbol = mod_map.get(modulation, 2)

    start_time = time.time()

    snr_linear = 10 ** (snr_db / 10.0)
    noise_var = 1.0 / snr_linear

    if SIONNA_AVAILABLE:
        tx_points, rx_points = _sionna_constellation(
            bits_per_symbol, num_symbols, noise_var, channel
        )
    else:
        tx_points, rx_points = _numpy_constellation(
            bits_per_symbol, num_symbols, noise_var, channel
        )

    # Compute EVM
    error_vec = rx_points - tx_points
    evm_rms = np.sqrt(np.mean(np.abs(error_vec) ** 2)) / np.sqrt(np.mean(np.abs(tx_points) ** 2))
    evm_percent = evm_rms * 100

    # Generate plot
    plot_b64 = _generate_constellation_plot(tx_points, rx_points, modulation, snr_db, channel, evm_percent)

    elapsed = time.time() - start_time

    return {
        "plot": plot_b64,
        "evm_percent": round(float(evm_percent), 2),
        "evm_db": round(float(20 * np.log10(evm_rms + 1e-12)), 2),
        "num_symbols": num_symbols,
        "metadata": {
            "modulation": modulation,
            "snr_db": snr_db,
            "channel": channel,
            "bits_per_symbol": bits_per_symbol,
            "elapsed_seconds": round(elapsed, 3),
            "engine": "sionna" if SIONNA_AVAILABLE else "numpy_fallback",
            "seed": seed
        }
    }


def _sionna_constellation(bits_per_symbol, num_symbols, noise_var, channel):
    """Generate constellation using Sionna with native AWGN block."""
    num_bits = num_symbols * bits_per_symbol

    constellation = Constellation("qam", num_bits_per_symbol=bits_per_symbol)
    mapper = Mapper(constellation=constellation)
    source = BinarySource()
    awgn = AWGN()

    bits = source([1, num_bits])
    x = mapper(bits)

    # Keep as PyTorch tensor for Sionna channel processing
    no_tensor = torch.tensor(noise_var, dtype=torch.float32)

    # Apply channel using Sionna blocks
    if channel == "rayleigh":
        h = torch.sqrt(torch.tensor(0.5)) * (
            torch.randn_like(x) + 1j * torch.randn_like(x))
        y = awgn(h * x, no_tensor)
        y = y / h
    elif channel == "rician":
        K = 10.0
        h_los = torch.sqrt(torch.tensor(K / (K + 1)))
        h_nlos = torch.sqrt(torch.tensor(1 / (2 * (K + 1)))) * (
            torch.randn_like(x) + 1j * torch.randn_like(x))
        h = h_los + h_nlos
        y = awgn(h * x, no_tensor)
        y = y / h
    else:  # AWGN
        y = awgn(x, no_tensor)

    # Convert to numpy for plotting
    x_np = x.detach().cpu().numpy().flatten()
    y_np = y.detach().cpu().numpy().flatten()

    return x_np, y_np


def _numpy_constellation(bits_per_symbol, num_symbols, noise_var, channel):
    """Fallback constellation generation using NumPy."""
    M = 2 ** bits_per_symbol
    sqrt_M = int(np.sqrt(M))

    # Generate QAM constellation points
    real_vals = np.arange(-(sqrt_M - 1), sqrt_M, 2)
    imag_vals = np.arange(-(sqrt_M - 1), sqrt_M, 2)
    constellation_points = []
    for r in real_vals:
        for i in imag_vals:
            constellation_points.append(complex(r, i))
    constellation_points = np.array(constellation_points[:M])

    # Normalize power
    avg_power = np.mean(np.abs(constellation_points) ** 2)
    constellation_points = constellation_points / np.sqrt(avg_power)

    # Random symbol selection
    indices = np.random.randint(0, M, num_symbols)
    tx = constellation_points[indices]

    # Apply channel
    if channel == "rayleigh":
        h = (np.random.randn(num_symbols) + 1j * np.random.randn(num_symbols)) / np.sqrt(2)
        noise = np.sqrt(noise_var / 2) * (np.random.randn(num_symbols) + 1j * np.random.randn(num_symbols))
        rx = h * tx + noise
        rx = rx / h
    elif channel == "rician":
        K = 10.0
        h_los = np.sqrt(K / (K + 1))
        h_nlos = np.sqrt(1 / (2 * (K + 1))) * (np.random.randn(num_symbols) + 1j * np.random.randn(num_symbols))
        h = h_los + h_nlos
        noise = np.sqrt(noise_var / 2) * (np.random.randn(num_symbols) + 1j * np.random.randn(num_symbols))
        rx = h * tx + noise
        rx = rx / h
    else:
        noise = np.sqrt(noise_var / 2) * (np.random.randn(num_symbols) + 1j * np.random.randn(num_symbols))
        rx = tx + noise

    return tx, rx


def _generate_constellation_plot(tx, rx, modulation, snr_db, channel, evm):
    """Create a visually rich constellation diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(8, 8), facecolor='#0a0a1a')
    ax.set_facecolor('#0a0a1a')

    # Plot RX points first (background)
    ax.scatter(
        np.real(rx), np.imag(rx),
        c='#00d4ff', alpha=0.15, s=8, marker='.',
        label=f'RX ({len(rx)} symbols)', zorder=1
    )

    # Plot TX constellation points (foreground)
    tx_unique = np.unique(np.round(tx, 6))
    ax.scatter(
        np.real(tx_unique), np.imag(tx_unique),
        c='#ff6b35', alpha=0.9, s=80, marker='x',
        linewidths=2, label='TX Reference', zorder=2
    )

    # Grid and axis lines
    ax.axhline(y=0, color='#333355', linewidth=0.5, linestyle='-')
    ax.axvline(x=0, color='#333355', linewidth=0.5, linestyle='-')
    ax.grid(True, alpha=0.15, color='#444466')

    # Labels and title
    ax.set_xlabel('In-Phase (I)', color='#aaaacc', fontsize=12)
    ax.set_ylabel('Quadrature (Q)', color='#aaaacc', fontsize=12)
    ax.set_title(
        f'{modulation.upper()} | SNR={snr_db}dB | {channel.upper()} | EVM={evm:.1f}%',
        color='#ffffff', fontsize=14, fontweight='bold', pad=15
    )

    ax.legend(loc='upper right', facecolor='#1a1a2e', edgecolor='#333355',
              labelcolor='#aaaacc', fontsize=10)
    ax.tick_params(colors='#666688')
    for spine in ax.spines.values():
        spine.set_color('#333355')

    plt.tight_layout()

    # Convert to base64
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='#0a0a1a')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')
