"""
app.py
------
This is the entry point you run with:  streamlit run app.py

HOW STREAMLIT WORKS (important to understand before reading further):
- Every time the user interacts with a widget (clicks a button, types in a box),
  Streamlit re-runs THIS ENTIRE FILE from top to bottom.
- Streamlit keeps track of widget values automatically between reruns.
- st.session_state is used when we need to remember something across reruns
  that isn't tied to a single widget (we don't need it much in this simple app).

STRUCTURE OF THIS APP:
- A sidebar with a radio button acts as our "page navigation".
- Depending on which page is selected, we show a different function's UI.
- All actual data logic lives in database.py - this file is just the UI layer.
"""

import streamlit as st
import pandas as pd
from datetime import date
import database as db

# ---- Page setup (must be the first Streamlit command) ----
st.set_page_config(page_title="Machine Maintenance Manager", layout="wide")

# Make sure the database and tables exist before anything else runs.
db.init_db()


# ============ PAGE FUNCTIONS ============
# Each function below renders one "page" of the app.

def page_dashboard():
    st.title("🛠️ Maintenance Dashboard")

    status_list = db.get_maintenance_status()

    if not status_list:
        st.info("No machines registered yet. Go to 'Register Machine' to add one.")
        return

    df = pd.DataFrame(status_list)

    # ---- Summary metrics at the top ----
    total = len(df)
    overdue = (df["status"] == "Overdue").sum()
    due_soon = (df["status"] == "Due Soon").sum()
    ok = (df["status"] == "OK").sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Machines", total)
    col2.metric("Overdue", overdue)
    col3.metric("Due Soon (≤7 days)", due_soon)
    col4.metric("OK", ok)

    st.divider()

    # ---- Alerts section ----
    st.subheader("🔔 Alerts")
    alerts = df[df["status"].isin(["Overdue", "Due Soon"])]
    if alerts.empty:
        st.success("No overdue or upcoming maintenance. All machines are on schedule.")
    else:
        for _, row in alerts.iterrows():
            if row["status"] == "Overdue":
                st.error(
                    f"**{row['name']}** ({row['location']}) — "
                    f"Overdue by {abs(row['days_remaining'])} day(s). "
                    f"Was due {row['next_due']}."
                )
            else:
                st.warning(
                    f"**{row['name']}** ({row['location']}) — "
                    f"Due in {row['days_remaining']} day(s) on {row['next_due']}."
                )

    st.divider()

    # ---- Full status table ----
    st.subheader("All Machines")

    def highlight_status(val):
        color = {"Overdue": "#ffcccc", "Due Soon": "#fff3cd", "OK": "#d4edda"}.get(val, "")
        return f"background-color: {color}"

    display_df = df[["name", "machine_type", "location", "last_service",
                      "next_due", "days_remaining", "status"]]
    display_df.columns = ["Name", "Type", "Location", "Last Service",
                           "Next Due", "Days Remaining", "Status"]

    st.dataframe(
        display_df.style.applymap(highlight_status, subset=["Status"]),
        use_container_width=True,
        hide_index=True,
    )


def page_register_machine():
    st.title("➕ Register New Machine")

    with st.form("register_machine_form", clear_on_submit=True):
        name = st.text_input("Machine Name *", placeholder="e.g. CNC Lathe 01")
        machine_type = st.text_input("Machine Type", placeholder="e.g. Lathe, Compressor")
        location = st.text_input("Location", placeholder="e.g. Building A, Floor 2")
        installation_date = st.date_input("Installation Date", value=date.today())
        frequency_days = st.number_input(
            "Maintenance Frequency (days) *",
            min_value=1, value=90, step=1,
            help="How often should this machine be serviced? e.g. 90 = every 3 months"
        )

        submitted = st.form_submit_button("Register Machine")

        if submitted:
            if not name.strip():
                st.error("Machine name is required.")
            else:
                db.add_machine(
                    name.strip(), machine_type.strip(), location.strip(),
                    installation_date.isoformat(), int(frequency_days)
                )
                st.success(f"Machine '{name}' registered successfully!")

    st.divider()
    st.subheader("Registered Machines")
    machines = db.get_all_machines()
    if machines:
        df = pd.DataFrame([dict(m) for m in machines])
        st.dataframe(
            df[["name", "machine_type", "location", "installation_date",
                "maintenance_frequency_days"]],
            use_container_width=True, hide_index=True,
        )

        with st.expander("Delete a machine"):
            options = {f"{m['name']} (ID {m['id']})": m["id"] for m in machines}
            choice = st.selectbox("Select machine to delete", list(options.keys()))
            if st.button("Delete", type="primary"):
                db.delete_machine(options[choice])
                st.success("Machine deleted.")
                st.rerun()
    else:
        st.info("No machines registered yet.")


def page_add_maintenance():
    st.title("🧾 Add Maintenance Record")

    machines = db.get_all_machines()
    if not machines:
        st.warning("Register a machine first before adding maintenance records.")
        return

    options = {f"{m['name']} (ID {m['id']})": m["id"] for m in machines}

    with st.form("add_record_form", clear_on_submit=True):
        machine_choice = st.selectbox("Machine *", list(options.keys()))
        service_date = st.date_input("Service Date", value=date.today())
        technician = st.text_input("Technician Name")
        description = st.text_area("Work Description", placeholder="What was done?")

        submitted = st.form_submit_button("Save Record")

        if submitted:
            machine_id = options[machine_choice]
            db.add_maintenance_record(
                machine_id, service_date.isoformat(), technician.strip(), description.strip()
            )
            st.success("Maintenance record saved. Next due date has been recalculated.")

    st.divider()
    st.subheader("Maintenance History")
    machine_choice = st.selectbox(
        "View history for", list(options.keys()), key="history_select"
    )
    records = db.get_records_for_machine(options[machine_choice])
    if records:
        df = pd.DataFrame([dict(r) for r in records])
        st.dataframe(
            df[["service_date", "technician", "description"]],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No maintenance records for this machine yet.")


def page_schedule():
    st.title("📅 Maintenance Schedule")

    status_list = db.get_maintenance_status()
    if not status_list:
        st.info("No machines registered yet.")
        return

    df = pd.DataFrame(status_list)
    df = df.sort_values("days_remaining", na_position="last")

    st.dataframe(
        df[["name", "location", "last_service", "next_due", "days_remaining", "status"]]
        .rename(columns={
            "name": "Machine", "location": "Location", "last_service": "Last Service",
            "next_due": "Next Due Date", "days_remaining": "Days Remaining", "status": "Status"
        }),
        use_container_width=True, hide_index=True,
    )


# ============ SIDEBAR NAVIGATION ============
st.sidebar.title("🏭 Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Dashboard", "Register Machine", "Add Maintenance Record", "Maintenance Schedule"],
)

if page == "Dashboard":
    page_dashboard()
elif page == "Register Machine":
    page_register_machine()
elif page == "Add Maintenance Record":
    page_add_maintenance()
elif page == "Maintenance Schedule":
    page_schedule()
