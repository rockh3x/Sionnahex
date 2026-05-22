"""
SQLite Database Manager for Sionnah3x Research Assistant.
Stores simulation history, parameters, results, and research notes.

Schema supports:
    - Simulation parameters and full results (JSON)
    - Research notes and tags for thesis organization
    - Random seed for reproducibility
    - Environment snapshot (Python, Sionna, PyTorch versions)
"""

import sqlite3
import json
import os
import sys
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sionna_research.db")


def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema with migration support."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create main table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sim_type TEXT NOT NULL,
            name TEXT,
            parameters TEXT NOT NULL,
            results TEXT NOT NULL,
            notes TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            seed INTEGER,
            environment TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add new columns to existing databases
    existing_columns = [row[1] for row in cursor.execute("PRAGMA table_info(simulations)").fetchall()]

    if "notes" not in existing_columns:
        cursor.execute("ALTER TABLE simulations ADD COLUMN notes TEXT DEFAULT ''")
    if "tags" not in existing_columns:
        cursor.execute("ALTER TABLE simulations ADD COLUMN tags TEXT DEFAULT ''")
    if "seed" not in existing_columns:
        cursor.execute("ALTER TABLE simulations ADD COLUMN seed INTEGER")
    if "environment" not in existing_columns:
        cursor.execute("ALTER TABLE simulations ADD COLUMN environment TEXT DEFAULT ''")
    if "is_favorite" not in existing_columns:
        cursor.execute("ALTER TABLE simulations ADD COLUMN is_favorite INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


def _get_environment():
    """Capture current environment for reproducibility."""
    env = {
        "python_version": sys.version.split()[0],
    }
    try:
        import torch
        env["pytorch_version"] = torch.__version__
        env["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            env["gpu_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    try:
        import sionna
        env["sionna_version"] = getattr(sionna, '__version__', 'unknown')
    except ImportError:
        pass
    return json.dumps(env)


def save_simulation(sim_type, name, parameters, results):
    """Save a simulation run to the database."""
    conn = get_connection()
    cursor = conn.cursor()

    # Extract seed from results metadata if available
    seed = None
    if isinstance(results, dict):
        meta = results.get("metadata", {})
        seed = meta.get("seed", None)

    cursor.execute(
        """INSERT INTO simulations
        (sim_type, name, parameters, results, seed, environment)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (sim_type, name, json.dumps(parameters), json.dumps(results),
         seed, _get_environment())
    )
    conn.commit()
    sim_id = cursor.lastrowid
    conn.close()
    return sim_id


def get_simulations(limit=50, sim_type=None):
    """Retrieve simulation history."""
    conn = get_connection()
    cursor = conn.cursor()
    if sim_type:
        cursor.execute(
            "SELECT * FROM simulations WHERE sim_type = ? ORDER BY created_at DESC LIMIT ?",
            (sim_type, limit)
        )
    else:
        cursor.execute(
            "SELECT * FROM simulations ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
    rows = cursor.fetchall()
    conn.close()
    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "sim_type": row["sim_type"],
            "name": row["name"],
            "parameters": json.loads(row["parameters"]),
            "results": json.loads(row["results"]),
            "notes": row["notes"] or "",
            "tags": row["tags"] or "",
            "seed": row["seed"],
            "is_favorite": bool(row["is_favorite"]) if "is_favorite" in row.keys() else False,
            "created_at": row["created_at"]
        })
    return results


def get_simulation_by_id(sim_id):
    """Retrieve a single simulation by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM simulations WHERE id = ?", (sim_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row["id"],
            "sim_type": row["sim_type"],
            "name": row["name"],
            "parameters": json.loads(row["parameters"]),
            "results": json.loads(row["results"]),
            "notes": row["notes"] or "",
            "tags": row["tags"] or "",
            "seed": row["seed"],
            "is_favorite": bool(row["is_favorite"]) if "is_favorite" in row.keys() else False,
            "environment": row["environment"] or "",
            "created_at": row["created_at"]
        }
    return None


def update_simulation_notes(sim_id, notes="", tags=""):
    """Update notes and tags for a simulation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE simulations SET notes = ?, tags = ? WHERE id = ?",
        (notes, tags, sim_id)
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def delete_simulation(sim_id):
    """Delete a simulation by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM simulations WHERE id = ?", (sim_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def get_simulation_count():
    """Get total simulation count and counts by type."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM simulations")
    total = cursor.fetchone()["total"]
    cursor.execute("SELECT sim_type, COUNT(*) as count FROM simulations GROUP BY sim_type")
    by_type = {row["sim_type"]: row["count"] for row in cursor.fetchall()}
    conn.close()
    return {"total": total, "by_type": by_type}


def get_analytics():
    """Get comprehensive analytics for the dashboard."""
    conn = get_connection()
    cursor = conn.cursor()

    # Simulation distribution by type
    cursor.execute("SELECT sim_type, COUNT(*) as count FROM simulations GROUP BY sim_type")
    distribution = {row["sim_type"]: row["count"] for row in cursor.fetchall()}

    # Total count
    cursor.execute("SELECT COUNT(*) as total FROM simulations")
    total = cursor.fetchone()["total"]

    # Daily activity (last 14 days)
    cursor.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM simulations
        WHERE created_at >= DATE('now', '-14 days')
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    """)
    daily_activity = [{"day": row["day"], "count": row["count"]} for row in cursor.fetchall()]

    # Recent simulations (last 5) with minimal data for sparkline
    cursor.execute("""
        SELECT id, name, sim_type, results, created_at
        FROM simulations
        WHERE sim_type = 'ber'
        ORDER BY created_at DESC
        LIMIT 10
    """)
    ber_trends = []
    for row in cursor.fetchall():
        try:
            results = json.loads(row["results"])
            ber_values = results.get("ber_values", [])
            min_ber = min([b for b in ber_values if b > 0], default=0)
            ber_trends.append({
                "id": row["id"],
                "name": row["name"],
                "min_ber": min_ber,
                "created_at": row["created_at"]
            })
        except (json.JSONDecodeError, ValueError):
            pass

    # Most used modulation
    cursor.execute("""
        SELECT parameters FROM simulations WHERE sim_type = 'ber'
    """)
    mod_counts = {}
    for row in cursor.fetchall():
        try:
            params = json.loads(row["parameters"])
            mod = params.get("modulation", "unknown")
            mod_counts[mod] = mod_counts.get(mod, 0) + 1
        except json.JSONDecodeError:
            pass

    conn.close()
    return {
        "total": total,
        "distribution": distribution,
        "daily_activity": daily_activity,
        "ber_trends": ber_trends,
        "modulation_usage": mod_counts
    }


def search_simulations(query, sim_type=None, limit=50):
    """Search simulations by name, notes, or parameters."""
    conn = get_connection()
    cursor = conn.cursor()
    search_term = f"%{query}%"

    if sim_type:
        cursor.execute("""
            SELECT * FROM simulations
            WHERE sim_type = ?
              AND (name LIKE ? OR notes LIKE ? OR parameters LIKE ?)
            ORDER BY created_at DESC LIMIT ?
        """, (sim_type, search_term, search_term, search_term, limit))
    else:
        cursor.execute("""
            SELECT * FROM simulations
            WHERE name LIKE ? OR notes LIKE ? OR parameters LIKE ?
            ORDER BY created_at DESC LIMIT ?
        """, (search_term, search_term, search_term, limit))

    rows = cursor.fetchall()
    conn.close()
    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "sim_type": row["sim_type"],
            "name": row["name"],
            "parameters": json.loads(row["parameters"]),
            "results": json.loads(row["results"]),
            "notes": row["notes"] or "",
            "tags": row["tags"] or "",
            "seed": row["seed"],
            "created_at": row["created_at"]
        })
    return results


def toggle_favorite(sim_id):
    """Toggle favorite status for a simulation. Returns new state."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_favorite FROM simulations WHERE id = ?", (sim_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    new_val = 0 if row["is_favorite"] else 1
    cursor.execute("UPDATE simulations SET is_favorite = ? WHERE id = ?", (new_val, sim_id))
    conn.commit()
    conn.close()
    return bool(new_val)
