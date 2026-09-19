"""
database.py
-----------
This file is the ONLY place that talks directly to the database.
Every other part of the app (app.py) calls functions from here instead
of writing raw SQL itself. This keeps things organized: if you ever
change database engines (e.g. SQLite -> PostgreSQL), you only edit this file.

Logic overview:
- machines table: one row per physical machine.
- maintenance_records table: one row per time a machine was serviced.
- We don't store "next due date" as a fixed value. Instead we CALCULATE it
  each time from: last_service_date + maintenance_frequency_days.
  This means the schedule is always self-updating and never goes stale.
"""

import sqlite3
from datetime import datetime, timedelta

DB_NAME = "machines.db"


def get_connection():
    """Open a connection to the SQLite database file.
    Every function below opens its own connection and closes it when done,
    which is the simplest safe pattern for a small Streamlit app."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row["name"]
    return conn


def init_db():
    """Create tables if they don't already exist. Safe to call every time
    the app starts - it won't wipe existing data."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            machine_type TEXT,
            location TEXT,
            installation_date TEXT,
            maintenance_frequency_days INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id INTEGER NOT NULL,
            service_date TEXT NOT NULL,
            technician TEXT,
            description TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (machine_id) REFERENCES machines (id)
        )
    """)

    conn.commit()
    conn.close()


# ---------- MACHINE FUNCTIONS ----------

def add_machine(name, machine_type, location, installation_date, frequency_days):
    """Insert a new machine into the machines table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO machines (name, machine_type, location, installation_date,
                               maintenance_frequency_days, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, machine_type, location, installation_date, frequency_days,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_all_machines():
    """Return every machine as a list of dict-like rows."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM machines ORDER BY name").fetchall()
    conn.close()
    return rows


def get_machine_by_id(machine_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
    conn.close()
    return row


def delete_machine(machine_id):
    """Delete a machine and its maintenance history (cascade manually,
    since plain SQLite doesn't enforce foreign keys by default)."""
    conn = get_connection()
    conn.execute("DELETE FROM maintenance_records WHERE machine_id = ?", (machine_id,))
    conn.execute("DELETE FROM machines WHERE id = ?", (machine_id,))
    conn.commit()
    conn.close()


# ---------- MAINTENANCE RECORD FUNCTIONS ----------

def add_maintenance_record(machine_id, service_date, technician, description):
    conn = get_connection()
    conn.execute("""
        INSERT INTO maintenance_records (machine_id, service_date, technician,
                                          description, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (machine_id, service_date, technician, description, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_records_for_machine(machine_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM maintenance_records
        WHERE machine_id = ?
        ORDER BY service_date DESC
    """, (machine_id,)).fetchall()
    conn.close()
    return rows


def get_last_service_date(machine_id):
    """Return the most recent service_date for a machine, or None if it
    has never been serviced (in which case we fall back to installation_date)."""
    conn = get_connection()
    row = conn.execute("""
        SELECT service_date FROM maintenance_records
        WHERE machine_id = ?
        ORDER BY service_date DESC LIMIT 1
    """, (machine_id,)).fetchone()
    conn.close()
    return row["service_date"] if row else None


# ---------- SCHEDULE / ALERT LOGIC ----------

def get_maintenance_status():
    """
    This is the core 'business logic' of the app.
    For every machine, work out:
      - last service date (or installation date if never serviced)
      - next due date = last service date + frequency_days
      - days_remaining = next due date - today
      - status = 'Overdue' / 'Due Soon' (within 7 days) / 'OK'

    Returns a list of dicts, one per machine, ready to display in a table.
    """
    machines = get_all_machines()
    today = datetime.now().date()
    status_list = []

    for m in machines:
        last_service = get_last_service_date(m["id"])
        base_date_str = last_service if last_service else m["installation_date"]

        if base_date_str:
            base_date = datetime.fromisoformat(base_date_str).date()
            next_due = base_date + timedelta(days=m["maintenance_frequency_days"])
            days_remaining = (next_due - today).days

            if days_remaining < 0:
                status = "Overdue"
            elif days_remaining <= 7:
                status = "Due Soon"
            else:
                status = "OK"
        else:
            next_due = None
            days_remaining = None
            status = "No Data"

        status_list.append({
            "id": m["id"],
            "name": m["name"],
            "machine_type": m["machine_type"],
            "location": m["location"],
            "last_service": base_date_str,
            "next_due": next_due.isoformat() if next_due else "N/A",
            "days_remaining": days_remaining,
            "status": status,
        })

    return status_list
