[README.md](https://github.com/user-attachments/files/28136607/README.md)
# Sionnah3x Research Assistant

**PhD-Grade Research Workbench for 6G Wireless Communication Simulations**

Sionnah3x Research Assistant is a powerful web application built on top of NVIDIA's Sionna library, PyTorch, and Flask. It provides a comprehensive, interactive set of tools for researchers to simulate, visualize, and export data for next-generation physical layer wireless research.

## Features

- **BER/BLER Analysis:** Evaluate Bit Error Rate (BER) and Block Error Rate (BLER) with theoretical validation across various modulations and channel models.
- **Constellation Diagrams:** Generate visual constellation diagrams and measure Error Vector Magnitude (EVM).
- **Channel Modeling:** Simulate 3GPP TDL channel models with customizable delay spreads and power profiles.
- **OFDM Systems:** Run End-to-End OFDM system simulations including subcarrier mapping, cyclic prefix, and equalization.
- **Parameter Sweeps:** Run comprehensive parameter sweep simulations to compare different configurations easily.
- **Data Export:** Export simulation results to CSV (for Excel/MATLAB) or LaTeX tabular formats directly for academic publications.
- **Database Tracking:** Save, search, and manage all your historical simulation runs with custom research notes and tags via an SQLite database.
- **Report Generation:** Create and export detailed, publication-ready HTML reports summarizing multiple simulation configurations and results.

## Requirements

Ensure you have Python 3.8+ installed. The main dependencies are:
- `torch` (PyTorch)
- `sionna` (NVIDIA Sionna)
- `flask` & `flask-cors`
- `numpy`
- `matplotlib`

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/sionna-6g-research-assistant.git
cd sionna-6g-research-assistant
```

2. Install the required packages using `pip`:
```bash
pip install -r requirements.txt
```

*(Note: Depending on your hardware, you might want to install the CUDA-enabled version of PyTorch for GPU-accelerated simulations.)*

## Usage

1. Start the Flask server:
```bash
python app.py
```

2. Open your web browser and navigate to:
```text
http://localhost:5000
```

3. Configure your simulation parameters via the web interface, execute runs, and explore the analytical results dynamically.

## Architecture

- `app.py`: The main Flask application handling API routes and backend logic.
- `database.py`: Manages the SQLite database (`sionna_research.db`) for simulation history and annotations.
- `simulations/`: Contains the simulation engine scripts for BER, Constellation, OFDM, and Channel modeling.
- `static/` & `templates/`: Contains the frontend UI assets (HTML, CSS, JS) delivering an interactive research dashboard.

## Acknowledgments

- Built using the [NVIDIA Sionna](https://nvlabs.github.io/sionna/) open-source library for link-level simulations.
