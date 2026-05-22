"""
Theoretical BER Reference Curves
Closed-form BER expressions for validation of simulated results.

References:
    - J. G. Proakis, "Digital Communications," 5th Ed., McGraw-Hill, 2008.
    - A. Goldsmith, "Wireless Communications," Cambridge University Press, 2005.
    - 3GPP TS 38.211: NR Physical Channels and Modulation.
"""

import numpy as np
from scipy.special import erfc, erfinv
from scipy.integrate import quad


# ═══════════════════════════════════════════════════════════════════════════
#  Q-Function and helpers
# ═══════════════════════════════════════════════════════════════════════════

def Q(x):
    """Gaussian Q-function: Q(x) = 0.5 * erfc(x / sqrt(2))."""
    return 0.5 * erfc(x / np.sqrt(2))


def Qinv(p):
    """Inverse Q-function."""
    return np.sqrt(2) * erfinv(1 - 2 * p)


# ═══════════════════════════════════════════════════════════════════════════
#  Theoretical BER over AWGN
# ═══════════════════════════════════════════════════════════════════════════

def ber_bpsk_awgn(snr_db):
    """Exact BER for BPSK over AWGN: Pb = Q(sqrt(2*Eb/N0))."""
    snr = 10 ** (np.asarray(snr_db, dtype=float) / 10.0)
    return Q(np.sqrt(2 * snr))


def ber_qpsk_awgn(snr_db):
    """
    Exact BER for QPSK over AWGN.
    QPSK with Gray coding has identical BER to BPSK per bit:
        Pb = Q(sqrt(2*Eb/N0))
    """
    return ber_bpsk_awgn(snr_db)


def ber_mqam_awgn(M, snr_db):
    """
    Approximate BER for M-QAM over AWGN (Gray-coded, square QAM).

    Formula (Proakis, 5th Ed., Eq. 4.3-32):
        Pb ≈ (4/log2(M)) * (1 - 1/sqrt(M)) * Q(sqrt(3*log2(M)*SNR / (M-1)))

    Valid for M = 4, 16, 64, 256 (square QAM constellations).
    """
    M = int(M)
    k = np.log2(M)
    snr = 10 ** (np.asarray(snr_db, dtype=float) / 10.0)
    # Eb/N0 = SNR / k for coded systems, but for uncoded BER curves
    # we use Es/N0 = k * Eb/N0, so Eb/N0 = snr
    ber = (4 / k) * (1 - 1 / np.sqrt(M)) * Q(np.sqrt(3 * k * snr / (M - 1)))
    return np.clip(ber, 1e-15, 0.5)


# ═══════════════════════════════════════════════════════════════════════════
#  Theoretical BER over Rayleigh Fading
# ═══════════════════════════════════════════════════════════════════════════

def ber_bpsk_rayleigh(snr_db):
    """
    Exact BER for BPSK over Rayleigh flat fading (Proakis Eq. 14.3-7):
        Pb = 0.5 * (1 - sqrt(γ / (1 + γ)))
    where γ = Eb/N0 (average SNR per bit).
    """
    gamma = 10 ** (np.asarray(snr_db, dtype=float) / 10.0)
    return 0.5 * (1 - np.sqrt(gamma / (1 + gamma)))


def ber_qpsk_rayleigh(snr_db):
    """QPSK over Rayleigh has same BER per bit as BPSK over Rayleigh (Gray coded)."""
    return ber_bpsk_rayleigh(snr_db)


def ber_mqam_rayleigh(M, snr_db):
    """
    Approximate BER for M-QAM over Rayleigh fading.

    Using the MGF-based approach (Goldsmith, Eq. 6.51):
        Pb ≈ (2/log2(M)) * (1 - 1/sqrt(M)) * Σ_{k=0}^{sqrt(M)/2 - 1}
              [1 - sqrt( (3*(2k+1)^2 * log2(M) * γ_avg) /
                         (2*(M-1) + 3*(2k+1)^2 * log2(M) * γ_avg) )]
    
    Simplified single-term approximation for typical use:
        Pb ≈ (2/log2(M)) * (1 - 1/sqrt(M)) * (1 - sqrt(1.5*γ*log2(M)/((M-1) + 1.5*γ*log2(M))))
    """
    M = int(M)
    k = np.log2(M)
    gamma = 10 ** (np.asarray(snr_db, dtype=float) / 10.0)
    
    g = 1.5 * k * gamma / (M - 1)
    ber = (2 / k) * (1 - 1 / np.sqrt(M)) * (1 - np.sqrt(g / (1 + g)))
    return np.clip(ber, 1e-15, 0.5)


# ═══════════════════════════════════════════════════════════════════════════
#  Theoretical BER over Rician Fading
# ═══════════════════════════════════════════════════════════════════════════

def ber_bpsk_rician(snr_db, K=10.0):
    """
    Approximate BER for BPSK over Rician fading.

    Using numerical integration of the conditional BER weighted by
    the Rician fading PDF. For large K, approaches AWGN performance.
    
    Args:
        snr_db: SNR values in dB
        K: Rician K-factor (ratio of LOS to scattered power)
    """
    snr_db = np.asarray(snr_db, dtype=float)
    ber = np.zeros_like(snr_db)
    
    for i, snr_db_val in enumerate(snr_db):
        gamma_avg = 10 ** (snr_db_val / 10.0)
        
        def integrand(x):
            # Rician PDF
            from scipy.special import i0
            pdf = 2 * (1 + K) * x * np.exp(-K - (1 + K) * x**2) * i0(2 * x * np.sqrt(K * (1 + K)))
            # Conditional BER for BPSK
            cond_ber = Q(np.sqrt(2 * gamma_avg * x**2))
            return pdf * cond_ber
        
        result, _ = quad(integrand, 0, 20)
        ber[i] = max(result, 1e-15)
    
    return ber


def ber_mqam_rician(M, snr_db, K=10.0):
    """
    Approximate BER for M-QAM over Rician fading.
    Interpolation between AWGN (K→∞) and Rayleigh (K=0).
    """
    ber_awgn = ber_mqam_awgn(M, snr_db)
    ber_ray = ber_mqam_rayleigh(M, snr_db)
    
    # Weight towards AWGN as K increases
    weight = K / (K + 1)
    ber = weight * ber_awgn + (1 - weight) * ber_ray
    return np.clip(ber, 1e-15, 0.5)


# ═══════════════════════════════════════════════════════════════════════════
#  Shannon Capacity
# ═══════════════════════════════════════════════════════════════════════════

def shannon_capacity(snr_db):
    """
    Shannon channel capacity: C = log2(1 + SNR) [bits/s/Hz].
    
    This is the theoretical maximum achievable spectral efficiency
    for an AWGN channel with a given SNR.
    """
    snr = 10 ** (np.asarray(snr_db, dtype=float) / 10.0)
    return np.log2(1 + snr)


def shannon_capacity_mimo(snr_db, n_tx, n_rx):
    """
    Ergodic capacity for i.i.d. Rayleigh MIMO channel:
        C = E[log2(det(I + (SNR/n_tx) * H * H^H))]
    
    Approximation using Jensen's inequality lower bound:
        C ≈ min(n_tx, n_rx) * log2(1 + SNR * max(n_tx, n_rx) / n_tx)
    """
    snr = 10 ** (np.asarray(snr_db, dtype=float) / 10.0)
    n_min = min(n_tx, n_rx)
    n_max = max(n_tx, n_rx)
    return n_min * np.log2(1 + snr * n_max / n_tx)


# ═══════════════════════════════════════════════════════════════════════════
#  LDPC Coding Gain Approximation
# ═══════════════════════════════════════════════════════════════════════════

def ber_coded_approximation(uncoded_ber_func, snr_db, coding_gain_db=3.0, **kwargs):
    """
    Approximate coded BER by shifting the uncoded curve by coding gain.
    
    For 5G NR LDPC with rate 1/2, typical coding gains:
        - At BER=1e-3: ~7-8 dB gain
        - At BER=1e-5: ~9-10 dB gain
        - Simplified: use ~3 dB average shift for visualization
    
    A more accurate model would use the EXIT chart or density evolution,
    but this provides a reasonable visual reference.
    """
    shifted_snr = np.asarray(snr_db, dtype=float) + coding_gain_db
    return uncoded_ber_func(shifted_snr, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
#  Master function: get theoretical BER for any configuration
# ═══════════════════════════════════════════════════════════════════════════

def get_theoretical_ber(snr_values, modulation, channel, coding="uncoded"):
    """
    Get theoretical BER values for a given configuration.
    
    Args:
        snr_values: list/array of SNR values in dB
        modulation: str ("bpsk", "qpsk", "16qam", "64qam", "256qam")
        channel: str ("awgn", "rayleigh", "rician")
        coding: str ("uncoded", "ldpc")
    
    Returns:
        dict with:
            - theoretical_ber: list of BER values
            - formula: str describing the formula used
            - reference: str citation
    """
    snr = np.asarray(snr_values, dtype=float)
    
    mod_map = {"bpsk": 2, "qpsk": 4, "16qam": 16, "64qam": 64, "256qam": 256}
    M = mod_map.get(modulation, 4)
    
    # Select the appropriate BER function
    if channel == "awgn":
        if modulation in ("bpsk", "qpsk"):
            ber_func = ber_bpsk_awgn
            formula = "P_b = Q(√(2·E_b/N_0))"
            reference = "Proakis, Digital Communications, 5th Ed., Eq. 4.2-21"
            ber = ber_func(snr)
        else:
            formula = f"P_b ≈ (4/log₂({M}))(1-1/√{M})·Q(√(3·log₂({M})·SNR/({M}-1)))"
            reference = "Proakis, Digital Communications, 5th Ed., Eq. 4.3-32"
            ber = ber_mqam_awgn(M, snr)
    
    elif channel == "rayleigh":
        if modulation in ("bpsk", "qpsk"):
            ber_func = ber_bpsk_rayleigh
            formula = "P_b = 0.5·(1 - √(γ/(1+γ)))"
            reference = "Proakis, Digital Communications, 5th Ed., Eq. 14.3-7"
            ber = ber_func(snr)
        else:
            formula = f"P_b ≈ (2/log₂({M}))(1-1/√{M})·(1-√(g/(1+g))), g=1.5·log₂({M})·γ/({M}-1)"
            reference = "Goldsmith, Wireless Communications, Eq. 6.51"
            ber = ber_mqam_rayleigh(M, snr)
    
    elif channel == "rician":
        if modulation in ("bpsk", "qpsk"):
            formula = "Numerical integration of Q(√(2γx²)) over Rician PDF, K=10"
            reference = "Simon & Alouini, Digital Comm. over Fading Channels, 2nd Ed."
            ber = ber_bpsk_rician(snr, K=10.0)
        else:
            formula = f"Weighted interpolation: w·BER_AWGN + (1-w)·BER_Rayleigh, w=K/(K+1)"
            reference = "Goldsmith, Wireless Communications, Ch. 6"
            ber = ber_mqam_rician(M, snr, K=10.0)
    else:
        ber = ber_bpsk_awgn(snr)
        formula = "Fallback: BPSK/AWGN"
        reference = "—"
    
    # Apply coding gain if needed
    if coding == "ldpc":
        # Shift by approximate coding gain
        coding_gain = 3.0  # Conservative estimate
        formula += f" + LDPC coding gain ≈ {coding_gain} dB shift"
        reference += " + 3GPP TS 38.212 (LDPC)"
        ber = get_theoretical_ber(
            (snr + coding_gain).tolist(), modulation, channel, "uncoded"
        )["theoretical_ber"]
        ber = [float(b) for b in ber]
    else:
        ber = [float(b) for b in ber]
    
    # Shannon capacity
    capacity = shannon_capacity(snr).tolist()
    
    return {
        "theoretical_ber": ber,
        "shannon_capacity": capacity,
        "formula": formula,
        "reference": reference
    }
