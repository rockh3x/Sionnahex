"""
Sionnah3x Research Assistant — Flask Application
PhD-grade research workbench for 6G wireless communication simulations.

Features:
    - BER/BLER analysis with theoretical validation
    - Constellation diagram generation with EVM
    - 3GPP TDL channel modeling
    - OFDM system simulation with equalization
    - Parameter sweep mode
    - CSV/LaTeX export for publications
    - Research notes and annotations
    - Full reproducibility via seed control
"""

from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import json
import csv
import io
import sys
import time
import traceback
from datetime import datetime

# Import database
from database import (
    init_db, save_simulation, get_simulations,
    get_simulation_by_id, delete_simulation, get_simulation_count,
    update_simulation_notes, get_analytics, search_simulations,
    toggle_favorite
)

# Import simulation engines
from simulations.ber_simulation import run_ber_simulation, run_ber_simulation_streaming
from simulations.constellation import run_constellation_simulation
from simulations.channel_sim import run_channel_simulation
from simulations.ofdm_sim import run_ofdm_simulation
from simulations.heatmap import generate_ber_heatmap

app = Flask(__name__)
CORS(app)

# Initialize database
init_db()


# ─── System Info ─────────────────────────────────────────────────────────────

def get_system_info():
    """Gather system information about available compute resources."""
    info = {
        "python_version": sys.version.split()[0],
        "sionna_available": False,
        "sionna_version": None,
        "pytorch_available": False,
        "pytorch_version": None,
        "cuda_available": False,
        "cuda_version": None,
        "gpu_name": None,
        "device": "cpu"
    }

    try:
        import torch
        info["pytorch_available"] = True
        info["pytorch_version"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["cuda_version"] = torch.version.cuda
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["device"] = "cuda"
    except ImportError:
        pass

    try:
        import sionna
        info["sionna_available"] = True
        info["sionna_version"] = getattr(sionna, '__version__', 'unknown')
    except ImportError:
        pass

    return info


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main application page."""
    return render_template("index.html")


@app.route("/api/system-info", methods=["GET"])
def system_info():
    """Return system/environment information."""
    info = get_system_info()
    counts = get_simulation_count()
    info["simulation_counts"] = counts
    return jsonify(info)


@app.route("/api/analytics", methods=["GET"])
def analytics():
    """Return comprehensive analytics for the dashboard."""
    try:
        data = get_analytics()
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── BER Simulation ─────────────────────────────────────────────────────────

@app.route("/api/simulate/ber", methods=["POST"])
def simulate_ber():
    """Run BER vs SNR simulation."""
    try:
        params = request.get_json()
        results = run_ber_simulation(params)

        # Save to database
        mod = params.get('modulation', 'qpsk').upper()
        ch = params.get('channel', 'awgn').upper()
        coding = params.get('coding', 'uncoded').upper()
        n_tx = params.get('num_tx', 1)
        n_rx = params.get('num_rx', 1)
        mimo_str = f"_{n_tx}x{n_rx}" if int(n_tx) > 1 or int(n_rx) > 1 else ""
        name = f"BER_{mod}_{ch}_{coding}{mimo_str}"
        sim_id = save_simulation("ber", name, params, results)
        results["sim_id"] = sim_id

        return jsonify({"status": "success", "data": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/simulate/ber-stream", methods=["POST"])
def simulate_ber_stream():
    """SSE endpoint for real-time BER simulation progress."""
    params = request.get_json()

    def generate():
        try:
            for event in run_ber_simulation_streaming(params):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


# ─── BER Sweep ──────────────────────────────────────────────────────────────

@app.route("/api/simulate/ber-sweep", methods=["POST"])
def simulate_ber_sweep():
    """Run multiple BER simulations varying one parameter (parameter sweep)."""
    try:
        params = request.get_json()
        sweep_param = params.get("sweep_param", "modulation")
        sweep_values = params.get("sweep_values", [])

        if not sweep_values:
            return jsonify({"status": "error", "message": "No sweep values provided"}), 400

        results = []
        for val in sweep_values:
            sim_params = dict(params)
            sim_params[sweep_param] = val
            # Remove sweep-specific keys
            sim_params.pop("sweep_param", None)
            sim_params.pop("sweep_values", None)

            result = run_ber_simulation(sim_params)

            # Build descriptive label
            mod = sim_params.get('modulation', 'qpsk').upper()
            ch = sim_params.get('channel', 'awgn').upper()
            coding = sim_params.get('coding', 'uncoded').upper()
            label = f"{mod}/{ch}/{coding}"

            result["label"] = label
            result["sweep_value"] = val

            # Save each to DB
            name = f"Sweep_{label}"
            sim_id = save_simulation("ber", name, sim_params, result)
            result["sim_id"] = sim_id

            results.append(result)

        return jsonify({"status": "success", "data": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── Heatmap Visualization ──────────────────────────────────────────────────

@app.route("/api/visualize/heatmap", methods=["POST"])
def visualize_heatmap():
    """Generate a BER heatmap from sweep results."""
    try:
        data = request.get_json()
        sweep_results = data.get("sweep_results", [])
        result = generate_ber_heatmap(sweep_results)
        if result:
            return jsonify({"status": "success", "data": result})
        return jsonify({"status": "error", "message": "Need at least 2 configurations"}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── Constellation Simulation ───────────────────────────────────────────────

@app.route("/api/simulate/constellation", methods=["POST"])
def simulate_constellation():
    """Generate constellation diagram."""
    try:
        params = request.get_json()
        results = run_constellation_simulation(params)

        name = f"Const_{params.get('modulation', 'qpsk').upper()}_{params.get('snr_db', 15)}dB"
        sim_id = save_simulation("constellation", name, params, results)
        results["sim_id"] = sim_id

        return jsonify({"status": "success", "data": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── Channel Simulation ─────────────────────────────────────────────────────

@app.route("/api/simulate/channel", methods=["POST"])
def simulate_channel():
    """Simulate channel response."""
    try:
        params = request.get_json()
        results = run_channel_simulation(params)

        name = f"Channel_{params.get('model', 'TDL-A')}"
        sim_id = save_simulation("channel", name, params, results)
        results["sim_id"] = sim_id

        return jsonify({"status": "success", "data": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── OFDM Simulation ────────────────────────────────────────────────────────

@app.route("/api/simulate/ofdm", methods=["POST"])
def simulate_ofdm():
    """Run OFDM system simulation."""
    try:
        params = request.get_json()
        results = run_ofdm_simulation(params)

        name = f"OFDM_{params.get('num_subcarriers', 256)}sc_{params.get('modulation', 'qpsk').upper()}"
        sim_id = save_simulation("ofdm", name, params, results)
        results["sim_id"] = sim_id

        return jsonify({"status": "success", "data": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── History ─────────────────────────────────────────────────────────────────

@app.route("/api/history", methods=["GET"])
def history():
    """Get simulation history with optional search."""
    limit = request.args.get("limit", 50, type=int)
    sim_type = request.args.get("type", None)
    query = request.args.get("q", None)
    if query:
        sims = search_simulations(query, sim_type=sim_type, limit=limit)
    else:
        sims = get_simulations(limit=limit, sim_type=sim_type)
    return jsonify({"status": "success", "data": sims})


@app.route("/api/history/<int:sim_id>", methods=["GET"])
def history_detail(sim_id):
    """Get a specific simulation."""
    sim = get_simulation_by_id(sim_id)
    if sim:
        return jsonify({"status": "success", "data": sim})
    return jsonify({"status": "error", "message": "Not found"}), 404


@app.route("/api/history/<int:sim_id>", methods=["DELETE"])
def history_delete(sim_id):
    """Delete a specific simulation."""
    if delete_simulation(sim_id):
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Not found"}), 404


# ─── Notes ───────────────────────────────────────────────────────────────────

@app.route("/api/history/<int:sim_id>/notes", methods=["PATCH"])
def update_notes(sim_id):
    """Update research notes and tags for a simulation."""
    try:
        data = request.get_json()
        notes = data.get("notes", "")
        tags = data.get("tags", "")
        if update_simulation_notes(sim_id, notes, tags):
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "Not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/history/<int:sim_id>/favorite", methods=["PATCH"])
def toggle_favorite_endpoint(sim_id):
    """Toggle favorite status for a simulation."""
    try:
        result = toggle_favorite(sim_id)
        if result is None:
            return jsonify({"status": "error", "message": "Not found"}), 404
        return jsonify({"status": "success", "is_favorite": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── Export ──────────────────────────────────────────────────────────────────

@app.route("/api/export/<int:sim_id>", methods=["GET"])
def export_simulation(sim_id):
    """Export simulation as JSON."""
    sim = get_simulation_by_id(sim_id)
    if sim:
        return jsonify(sim)
    return jsonify({"status": "error", "message": "Not found"}), 404


@app.route("/api/export/<int:sim_id>/csv", methods=["GET"])
def export_simulation_csv(sim_id):
    """Export simulation data as CSV for Excel/MATLAB/LaTeX."""
    sim = get_simulation_by_id(sim_id)
    if not sim:
        return jsonify({"status": "error", "message": "Not found"}), 404

    output = io.StringIO()
    results = sim.get("results", {})
    sim_type = sim.get("sim_type", "")

    if sim_type == "ber":
        writer = csv.writer(output)
        # Header with metadata
        meta = results.get("metadata", {})
        writer.writerow(["# Sionnah3x Research Assistant — BER Simulation Export"])
        writer.writerow([f"# Modulation: {meta.get('modulation', 'N/A').upper()}"])
        writer.writerow([f"# Channel: {meta.get('channel', 'N/A').upper()}"])
        writer.writerow([f"# Coding: {meta.get('coding', 'N/A').upper()}"])
        writer.writerow([f"# Seed: {meta.get('seed', 'N/A')}"])
        writer.writerow([f"# Engine: {meta.get('engine', 'N/A')}"])
        writer.writerow([f"# Date: {sim.get('created_at', '')}"])
        writer.writerow([])

        # Data columns
        snr = results.get("snr_values", [])
        ber = results.get("ber_values", [])
        bler = results.get("bler_values", [])
        thput = results.get("throughput", [])
        theo = results.get("theoretical_ber", [])
        shannon = results.get("shannon_capacity", [])
        stats = results.get("statistics", [])
        ci = results.get("confidence_intervals", [])

        writer.writerow([
            "SNR_dB", "BER_simulated", "BER_theoretical", "BLER",
            "Throughput_bps_Hz", "Shannon_Capacity_bps_Hz",
            "Num_Errors", "Num_Bits", "CI_95_lower", "CI_95_upper", "Iterations"
        ])

        for i in range(len(snr)):
            row = [
                snr[i],
                ber[i] if i < len(ber) else "",
                theo[i] if i < len(theo) else "",
                bler[i] if i < len(bler) else "",
                thput[i] if i < len(thput) else "",
                shannon[i] if i < len(shannon) else "",
                stats[i]["total_errors"] if i < len(stats) else "",
                stats[i]["total_bits"] if i < len(stats) else "",
                ci[i]["lower"] if i < len(ci) else "",
                ci[i]["upper"] if i < len(ci) else "",
                stats[i]["iterations"] if i < len(stats) else ""
            ]
            writer.writerow(row)

    elif sim_type == "constellation":
        writer = csv.writer(output)
        meta = results.get("metadata", {})
        writer.writerow(["# Constellation Simulation Export"])
        writer.writerow([f"# Modulation: {meta.get('modulation', '').upper()}"])
        writer.writerow([f"# SNR: {meta.get('snr_db', '')} dB"])
        writer.writerow([f"# Channel: {meta.get('channel', '').upper()}"])
        writer.writerow([])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["EVM_RMS_percent", results.get("evm_percent", "")])
        writer.writerow(["EVM_dB", results.get("evm_db", "")])
        writer.writerow(["Num_Symbols", results.get("num_symbols", "")])

    elif sim_type == "channel":
        writer = csv.writer(output)
        stats = results.get("statistics", {})
        writer.writerow(["# Channel Simulation Export"])
        writer.writerow([f"# Model: {stats.get('model', '')}"])
        writer.writerow([])
        writer.writerow(["Delay_ns", "Power_dB"])
        delays = results.get("delays_ns", [])
        powers = results.get("powers_db", [])
        for d, p in zip(delays, powers):
            writer.writerow([d, p])

    elif sim_type == "ofdm":
        writer = csv.writer(output)
        meta = results.get("metadata", {})
        writer.writerow(["# OFDM Simulation Export"])
        writer.writerow([f"# Subcarriers: {meta.get('num_subcarriers', '')}"])
        writer.writerow([f"# Modulation: {meta.get('modulation', '').upper()}"])
        writer.writerow([])
        writer.writerow(["Metric", "Value"])
        m = results.get("metrics", {})
        for key, val in m.items():
            writer.writerow([key, val])
        writer.writerow([])
        writer.writerow(["Equalizer", "BER"])
        ber_eq = results.get("ber_by_equalizer", {})
        for eq, ber in ber_eq.items():
            writer.writerow([eq.upper(), ber])

    else:
        writer = csv.writer(output)
        writer.writerow(["raw_json"])
        writer.writerow([json.dumps(results)])

    csv_content = output.getvalue()
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={
            "Content-Disposition": f"attachment; filename=simulation_{sim_id}.csv"
        }
    )


@app.route("/api/export/<int:sim_id>/latex", methods=["GET"])
def export_simulation_latex(sim_id):
    """Export BER simulation data as LaTeX tabular for papers."""
    sim = get_simulation_by_id(sim_id)
    if not sim:
        return jsonify({"status": "error", "message": "Not found"}), 404

    results = sim.get("results", {})
    sim_type = sim.get("sim_type", "")

    if sim_type != "ber":
        return jsonify({"status": "error", "message": "LaTeX export is only available for BER simulations"}), 400

    snr = results.get("snr_values", [])
    ber = results.get("ber_values", [])
    theo = results.get("theoretical_ber", [])
    bler = results.get("bler_values", [])
    meta = results.get("metadata", {})

    # Build LaTeX tabular
    latex = []
    latex.append(f"% Sionnah3x Research Assistant — BER Results")
    latex.append(f"% {meta.get('modulation', '').upper()} / {meta.get('channel', '').upper()} / {meta.get('coding', '').upper()}")
    latex.append(f"% Seed: {meta.get('seed', 'N/A')}")
    latex.append(r"\begin{table}[htbp]")
    latex.append(r"\centering")
    latex.append(f"\\caption{{BER vs SNR — {meta.get('modulation', '').upper()}, {meta.get('channel', '').upper()}, {meta.get('coding', '').upper()}}}")
    latex.append(r"\label{tab:ber_results}")
    latex.append(r"\begin{tabular}{cccc}")
    latex.append(r"\toprule")
    latex.append(r"SNR (dB) & BER (Sim.) & BER (Theo.) & BLER \\")
    latex.append(r"\midrule")

    for i in range(len(snr)):
        s = snr[i]
        b = f"{ber[i]:.2e}" if i < len(ber) and ber[i] > 0 else "0"
        t = f"{theo[i]:.2e}" if i < len(theo) and theo[i] > 0 else "0"
        bl = f"{bler[i]:.4f}" if i < len(bler) else "—"
        latex.append(f"{s} & {b} & {t} & {bl} \\\\")

    latex.append(r"\bottomrule")
    latex.append(r"\end{tabular}")
    latex.append(r"\end{table}")

    latex_str = "\n".join(latex)
    return Response(
        latex_str,
        mimetype='text/plain',
        headers={
            "Content-Disposition": f"attachment; filename=simulation_{sim_id}.tex"
        }
    )


# ─── Report Generator ────────────────────────────────────────────────────

@app.route("/api/export/report", methods=["POST"])
def export_report():
    """Generate an HTML research report from multiple simulations."""
    try:
        data = request.get_json()
        sim_ids = data.get("sim_ids", [])
        title = data.get("title", "Sionnah3x Research Report")

        if not sim_ids:
            return jsonify({"status": "error", "message": "No simulations selected"}), 400

        sims = []
        for sid in sim_ids:
            sim = get_simulation_by_id(sid)
            if sim:
                sims.append(sim)

        if not sims:
            return jsonify({"status": "error", "message": "No valid simulations found"}), 404

        # Build HTML report
        html = f"""<!DOCTYPE html>
<html><head><meta charset='UTF-8'>
<title>{title}</title>
<style>
  body {{ font-family: 'Inter', -apple-system, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #1a1a2e; line-height: 1.6; }}
  h1 {{ color: #0a0a1a; border-bottom: 3px solid #76B900; padding-bottom: 12px; }}
  h2 {{ color: #333; margin-top: 32px; }}
  .meta {{ font-size: 13px; color: #666; margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }}
  th {{ background: #f0f0f5; padding: 10px 12px; text-align: left; border-bottom: 2px solid #ddd; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
  .badge-ber {{ background: rgba(118,185,0,0.15); color: #76B900; }}
  .badge-constellation {{ background: rgba(0,212,255,0.12); color: #00aacc; }}
  .badge-channel {{ background: rgba(255,107,53,0.12); color: #ff6b35; }}
  .badge-ofdm {{ background: rgba(168,85,247,0.12); color: #a855f7; }}
  .sim-card {{ border: 1px solid #e0e0e8; border-radius: 12px; padding: 20px; margin: 20px 0; }}
  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 11px; color: #999; }}
</style>
</head><body>
<h1>📡 {title}</h1>
<div class='meta'>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Simulations: {len(sims)} · Created by <strong>rockh3x</strong> using Sionnah3x Research Assistant</div>
"""
        for sim in sims:
            params = sim.get('parameters', {})
            results = sim.get('results', {})
            meta = results.get('metadata', {})
            st = sim.get('sim_type', 'unknown')

            html += f"""<div class='sim-card'>
<h2>#{sim['id']} — {sim.get('name', 'Unnamed')} <span class='badge badge-{st}'>{st}</span></h2>
<p style='font-size:12px;color:#888;'>Created: {sim.get('created_at', '—')} · Seed: {sim.get('seed', '—')}</p>
"""
            # Parameters table
            html += "<table><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>"
            for k, v in params.items():
                html += f"<tr><td><strong>{k}</strong></td><td>{v}</td></tr>"
            html += "</tbody></table>"

            # BER results table
            if st == 'ber' and 'snr_values' in results:
                html += "<table><thead><tr><th>SNR (dB)</th><th>BER (Sim)</th><th>BER (Theo)</th><th>BLER</th></tr></thead><tbody>"
                snr = results.get('snr_values', [])
                ber = results.get('ber_values', [])
                theo = results.get('theoretical_ber', [])
                bler = results.get('bler_values', [])
                for i in range(len(snr)):
                    b = f"{ber[i]:.2e}" if i < len(ber) and ber[i] > 0 else "0"
                    t = f"{theo[i]:.2e}" if i < len(theo) and theo[i] > 0 else "0"
                    bl = f"{bler[i]:.4f}" if i < len(bler) else "—"
                    html += f"<tr><td>{snr[i]}</td><td>{b}</td><td>{t}</td><td>{bl}</td></tr>"
                html += "</tbody></table>"

            # Notes
            if sim.get('notes'):
                html += f"<p><strong>Notes:</strong> {sim['notes']}</p>"

            html += "</div>"

        html += f"""<div class='footer'>
<p>Sionnah3x Research Assistant · Built with NVIDIA Sionna 2.0, PyTorch, Flask · Created by rockh3x</p>
<p>Reference: W. Hoydis et al., "Sionna: An Open-Source Library for Next-Generation Physical Layer Research," arXiv:2203.11854, 2022.</p>
</div></body></html>"""

        return Response(
            html,
            mimetype='text/html',
            headers={
                "Content-Disposition": f"attachment; filename=research_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            }
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ─── Run Server ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import io as _io, os
    # Force UTF-8 output on Windows
    if os.name == 'nt':
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    print("\n" + "=" * 60)
    print("  [*] Sionnah3x Research Assistant — PhD Edition")
    print("  " + "-" * 35)

    info = get_system_info()
    print(f"  Python:  {info['python_version']}")
    print(f"  PyTorch: {info['pytorch_version'] or 'Not installed'}")
    print(f"  Sionna:  {info['sionna_version'] or 'Not installed (using fallback)'}")
    print(f"  CUDA:    {info['gpu_name'] or 'Not available (using CPU)'}")
    print(f"  Device:  {info['device']}")
    print("  " + "-" * 35)
    print("  Open http://localhost:5000 in your browser")
    print("=" * 60 + "\n")

    app.run(debug=True, host="127.0.0.1", port=5000)
