"""
BER Heatmap Generator
Creates publication-quality 2D heatmaps showing BER as a function
of SNR and modulation/configuration.

Used after parameter sweeps to visualize which configuration
wins at each SNR point.
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64


def generate_ber_heatmap(sweep_results):
    """
    Generate a heatmap from sweep results.

    Parameters:
        sweep_results: list of dicts, each with:
            - label: str (e.g., "QPSK/AWGN/Uncoded")
            - snr_values: list of float
            - ber_values: list of float

    Returns:
        dict with plot (base64 PNG) and metadata
    """
    if not sweep_results or len(sweep_results) < 2:
        return None

    labels = [r.get("label", f"Config {i+1}") for i, r in enumerate(sweep_results)]
    snr_values = sweep_results[0].get("snr_values", [])

    # Build BER matrix (configs × SNR points)
    ber_matrix = []
    for r in sweep_results:
        ber_row = r.get("ber_values", [])
        # Replace 0 with a small number for log scale
        ber_row = [max(b, 1e-8) for b in ber_row]
        ber_matrix.append(ber_row)

    ber_matrix = np.array(ber_matrix)
    log_ber = np.log10(ber_matrix)

    # Create figure
    fig, ax = plt.subplots(figsize=(10, max(3, len(labels) * 0.8)), dpi=200)
    fig.patch.set_facecolor('#0a0a1a')
    ax.set_facecolor('#0a0a1a')

    im = ax.imshow(
        log_ber, aspect='auto', cmap='inferno_r',
        interpolation='nearest',
        extent=[snr_values[0], snr_values[-1], len(labels) - 0.5, -0.5]
    )

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, pad=0.02)
    cbar.set_label('log₁₀(BER)', color='#aaa', fontsize=11)
    cbar.ax.tick_params(colors='#888', labelsize=9)

    # Axis labels
    ax.set_xlabel('Eb/N0 (dB)', color='#aaa', fontsize=12)
    ax.set_ylabel('Configuration', color='#aaa', fontsize=12)
    ax.set_title('BER Heatmap — Parameter Sweep', color='#e8e8f0',
                 fontsize=14, fontweight='bold', pad=12)

    # Y-axis labels
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=10)

    # Style ticks
    ax.tick_params(colors='#888', labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor('#333')

    # Annotate cells with BER values
    for i in range(len(labels)):
        for j in range(len(snr_values)):
            val = ber_matrix[i, j]
            text = f"{val:.0e}" if val > 1e-7 else "≈0"
            color = 'white' if log_ber[i, j] < -3 else 'black'
            ax.text(
                snr_values[j], i, text,
                ha='center', va='center', fontsize=7,
                color=color, fontweight='bold'
            )

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight',
                facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    plot_b64 = base64.b64encode(buf.read()).decode('utf-8')

    return {
        "plot": plot_b64,
        "num_configs": len(labels),
        "num_snr_points": len(snr_values),
        "labels": labels
    }
