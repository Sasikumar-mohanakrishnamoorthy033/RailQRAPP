# app.py
"""
Railway Material QR Tracking App
Roles:
- Admin: Bulk generate UIDs + QRs, assign tasks
- JE / Technical / PWI: Update inspection/fitted data (manual + QR scan)
- SRE: Inbox + Product view
- DRE: Inbox + Product view
- Zonal: Inbox + Product view (system overview)
"""

# ========================
# IMPORTS
# ========================
import os, csv, secrets, string
from datetime import datetime, timedelta

import streamlit as st
import qrcode
import pandas as pd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pyzbar.pyzbar import decode


# ========================
# CONFIG / FILE PATHS
# ========================
OUTPUT_DIR = "Generated_QRs"
USERS_FILE = "users.csv"
PRODUCT_DB = "product_database.csv"
TASKS_FILE = "tasks.csv"
ALERTS_FILE = "alerts.csv"

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ========================
# INITIAL SETUP: Ensure CSV files exist
# ========================
def ensure_csv_files_exist():
    if not os.path.exists(USERS_FILE):
        users = [
            {"EmployerID":"1001","Username":"admin1","Password":"Admin@123","Role":"Admin"},
            {"EmployerID":"1002","Username":"je01","Password":"JEpass01","Role":"JE"},
            {"EmployerID":"1003","Username":"tech01","Password":"TECHpass01","Role":"Technical"},
            {"EmployerID":"1004","Username":"pwi01","Password":"PWIpass01","Role":"PWI"},
            {"EmployerID":"1005","Username":"sre01","Password":"SREpass01","Role":"SRE"},
            {"EmployerID":"1006","Username":"dre01","Password":"DREpass01","Role":"DRE"},
            {"EmployerID":"1007","Username":"zonal01","Password":"ZONpass01","Role":"Zonal"},
        ]
        with open(USERS_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["EmployerID","Username","Password","Role"])
            w.writeheader()
            w.writerows(users)

    if not os.path.exists(PRODUCT_DB):
        df = pd.DataFrame(columns=[
            "UID","Type","VendorLot","MfgDate","ExpiryDate","WarrantyDays",
            "FittedDate","InspectionDate","Status","QRPath"
        ])
        df.to_csv(PRODUCT_DB, index=False)

    if not os.path.exists(TASKS_FILE):
        df = pd.DataFrame(columns=[
            "TaskID","UID","AssignedBy","AssignedTo","AssignedAt",
            "Status","LastUpdate","Remarks"
        ])
        df.to_csv(TASKS_FILE, index=False)

    if not os.path.exists(ALERTS_FILE):
        df = pd.DataFrame(columns=[
            "AlertID","UID","Type","CreatedAt","AssignedToRole",
            "AssignedTo","EscalatedTo","Status","Notes"
        ])
        df.to_csv(ALERTS_FILE, index=False)

ensure_csv_files_exist()


# ========================
# AUTHENTICATION
# ========================
def load_users():
    return pd.read_csv(USERS_FILE, dtype=str)

def authenticate(username, password):
    users = load_users()
    matched = users[(users["Username"]==username) & (users["Password"]==password)]
    if not matched.empty:
        return matched.iloc[0].to_dict()
    return None


# ========================
# QR CODE HELPERS
# ========================
def generate_unique_serial(length=4):
    return ''.join(secrets.choice(string.digits) for _ in range(length))

material_codes = {"elastic_clip":"EC", "rail_pad":"RP", "liner":"LN", "sleeper":"SL"}

def generate_uid(material, year, vendor, batch, serial):
    code = material_codes.get(material, "XX")
    return f"{code}{str(year)[-2:]}{vendor}{str(batch).zfill(3)}{serial.zfill(4)}"

def add_text_to_qr(img, text):
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    w,h = img.size
    draw.rectangle(((0,h-18),(w,h)), fill=(255,255,255))
    draw.text((5, h-15), text, font=font, fill=(0,0,0))
    return img

def generate_qrs_bulk(materials, vendor_lot, batch, quantity, vendor_code="A1", warranty_days=1825):
    generated = []
    for material in materials:
        for _ in range(quantity):
            year = datetime.now().year
            serial = generate_unique_serial(4)
            uid = generate_uid(material, year, vendor_code, batch, serial)

            mfg_date = datetime.now().date()
            expiry_date = mfg_date + timedelta(days=warranty_days)

            payload = f"UID:{uid};Type:{material};VendorLot:{vendor_lot};MfgDate:{mfg_date};ExpiryDate:{expiry_date};WarrantyDays:{warranty_days}"

            img = qrcode.make(payload).convert("RGB")
            img = add_text_to_qr(img, uid)
            file_path = os.path.join(OUTPUT_DIR, f"QR_{uid}.png")
            img.save(file_path)

            row = {
                "UID": uid,"Type": material,"VendorLot": vendor_lot,
                "MfgDate": str(mfg_date),"ExpiryDate": str(expiry_date),
                "WarrantyDays": str(warranty_days),
                "FittedDate": "","InspectionDate": "",
                "Status": "Pending","QRPath": file_path
            }

            df = pd.read_csv(PRODUCT_DB, dtype=str)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df.to_csv(PRODUCT_DB, index=False)

            generated.append(uid)
    return generated


# ========================
# PRODUCT OPERATIONS
# ========================
def find_product(uid):
    df = pd.read_csv(PRODUCT_DB, dtype=str)
    match = df[df["UID"]==uid]
    return None if match.empty else match.iloc[0].to_dict()

def update_product(uid, fitted_date=None, inspection_date=None, status=None):
    df = pd.read_csv(PRODUCT_DB, dtype=str)
    idx = df.index[df["UID"]==uid].tolist()
    if not idx:
        return False
    i = idx[0]
    if fitted_date: df.at[i,"FittedDate"] = fitted_date
    if inspection_date: df.at[i,"InspectionDate"] = inspection_date
    if status: df.at[i,"Status"] = status
    df.to_csv(PRODUCT_DB, index=False)
    return True


# ========================
# QR SCANNER
# ========================
def decode_qr_from_image(image_file):
    img = Image.open(image_file).convert("RGB")
    img_np = np.array(img)
    decoded_objs = decode(img_np)
    if decoded_objs:
        return decoded_objs[0].data.decode("utf-8")
    return None


# ========================
# TASK & ALERT MANAGEMENT
# ========================
def complete_task(uid, worker_username, role_name):
    df_tasks = pd.read_csv(TASKS_FILE)
    updated = False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for i, row in df_tasks.iterrows():
        if row["UID"] == uid and (row["AssignedTo"] == worker_username or row["AssignedTo"] == role_name) and row["Status"] == "Pending":
            df_tasks.at[i, "Status"] = "Completed"
            df_tasks.at[i, "LastUpdate"] = now
            updated = True
    df_tasks.to_csv(TASKS_FILE, index=False)
    return updated

def generate_alerts():
    df_tasks = pd.read_csv(TASKS_FILE)
    df_alerts = pd.read_csv(ALERTS_FILE)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _, row in df_tasks.iterrows():
        if not df_alerts[(df_alerts["UID"]==row["UID"]) & (df_alerts["Status"]=="Active")].empty:
            continue
        prod = find_product(row["UID"])
        if not prod: continue

        expiry = datetime.strptime(prod["ExpiryDate"], "%Y-%m-%d").date()
        days_to_expiry = (expiry - datetime.now().date()).days

        if row["Status"]=="Completed" and days_to_expiry <= 30:
            alert_id = pd.to_numeric(df_alerts["AlertID"], errors='coerce').max()
            alert_id = int(alert_id + 1) if not np.isnan(alert_id) else 1
            new_alert = {
                "AlertID": alert_id, "UID": row["UID"], "Type": "Near Expiry",
                "CreatedAt": now, "AssignedToRole": "SRE",
                "AssignedTo": "", "EscalatedTo": "",
                "Status": "Active", "Notes": f"{days_to_expiry} days to expiry"
            }
            df_alerts = pd.concat([df_alerts, pd.DataFrame([new_alert])], ignore_index=True)
    df_alerts.to_csv(ALERTS_FILE, index=False)

def create_assignment_alert(task):
    df_alerts = pd.read_csv(ALERTS_FILE)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    assigned_to = task["AssignedTo"]
    if assigned_to in ["JE", "Technical", "PWI"]:
        authority_role = "SRE"
    elif assigned_to == "SRE":
        authority_role = "DRE"
    else:
        authority_role = "Zonal"

    max_alert_id = pd.to_numeric(df_alerts["AlertID"], errors='coerce').max()
    alert_id = int(max_alert_id + 1) if not np.isnan(max_alert_id) else 1

    alert_row = {
        "AlertID": alert_id, "UID": task["UID"], "Type": "Task Assigned",
        "CreatedAt": now, "AssignedToRole": authority_role,
        "AssignedTo": task["AssignedTo"], "EscalatedTo": "",
        "Status": "Active", "Notes": f"Task {task['TaskID']} assigned to {task['AssignedTo']}"
    }
    df_alerts = pd.concat([df_alerts, pd.DataFrame([alert_row])], ignore_index=True)
    df_alerts.to_csv(ALERTS_FILE, index=False)


# ========================
# UI HELPERS
# ========================
def show_inbox(user):
    st.subheader("📩 Inbox Messages")
    df_alerts = pd.read_csv(ALERTS_FILE)
    role, username = user["Role"], user["Username"]

    relevant_alerts = df_alerts[
        (df_alerts["AssignedToRole"]==role) | (df_alerts["AssignedTo"]==username)
    ]

    if relevant_alerts.empty:
        st.info("No messages")
    else:
        for _, row in relevant_alerts.iterrows():
            st.markdown(f"*AlertID:* {row['AlertID']}")
            st.markdown(f"*UID:* {row['UID']}")
            st.markdown(f"*Type:* {row['Type']}")
            st.markdown(f"*Created At:* {row['CreatedAt']}")
            st.markdown(f"*Notes:* {row['Notes']}")
            status_color = "green" if row['Status']=="Active" else "red"
            st.markdown(
                f"*Status:* <span style='color:{status_color}'>{row['Status']}</span>",
                unsafe_allow_html=True
            )

            if st.button(f"Mark Alert {row['AlertID']} as Read", key=f"read_{row['AlertID']}"):
                df_alerts.loc[df_alerts["AlertID"]==row['AlertID'], "Status"] = "Read"
                df_alerts.to_csv(ALERTS_FILE, index=False)
                st.rerun()
            st.markdown("---")


def assign_task_panel(user):
    st.subheader("Assign Task to Worker / Role")
    df_products = pd.read_csv(PRODUCT_DB)
    df_users = pd.read_csv(USERS_FILE)

    uid = st.selectbox("Select Product UID", df_products["UID"].tolist())
    role_or_user = st.selectbox("Assign To", df_users["Username"].tolist() + df_users["Role"].unique().tolist())
    remarks = st.text_input("Remarks")

    if st.button("Assign Task"):
        df_tasks = pd.read_csv(TASKS_FILE)
        max_id = pd.to_numeric(df_tasks["TaskID"], errors="coerce").max()
        task_id = int(max_id + 1) if not np.isnan(max_id) else 1

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_task = {
            "TaskID": task_id, "UID": uid,
            "AssignedBy": user["Username"], "AssignedTo": role_or_user,
            "AssignedAt": timestamp, "Status": "Pending",
            "LastUpdate": timestamp, "Remarks": remarks
        }

        df_tasks = pd.concat([df_tasks, pd.DataFrame([new_task])], ignore_index=True)
        df_tasks.to_csv(TASKS_FILE, index=False)
        create_assignment_alert(new_task)

        st.success(f"Task {task_id} assigned to {role_or_user} and alert sent to authority")


# ========================
# PRODUCT VIEW (FOR SRE/DRE/ZONAL)
# ========================
def view_products_panel():
    st.subheader("📦 Product Database")
    df = pd.read_csv(PRODUCT_DB)

    if df.empty:
        st.warning("No products available yet.")
        return

    # Filters
    product_type = st.selectbox("Filter by Type", ["All"] + df["Type"].unique().tolist())
    status = st.selectbox("Filter by Status", ["All"] + df["Status"].unique().tolist())

    df_filtered = df.copy()
    if product_type != "All":
        df_filtered = df_filtered[df_filtered["Type"]==product_type]
    if status != "All":
        df_filtered = df_filtered[df_filtered["Status"]==status]

    st.dataframe(df_filtered)


# ========================
# UPDATE PANEL (JE / Technical / PWI)
# ========================
def update_panel(user, role_name):
    st.header(f"{role_name} Dashboard")
    show_inbox(user)

    # --- Manual entry ---
    st.subheader("Manual UID Entry")
    uid = st.text_input(f"Enter UID ({role_name})")
    if st.button(f"Fetch Product ({role_name})"):
        prod = find_product(uid)
        if prod:
            st.json(prod)
            fitted = st.date_input("Fitted Date", datetime.now().date(), key=f"fit_{role_name}")
            insp = st.date_input("Inspection Date", datetime.now().date(), key=f"insp_{role_name}")
            if st.button(f"Save Update (Manual) - {role_name}"):
                update_product(uid, str(fitted), str(insp), "Fitted")
                complete_task(uid, user["Username"], role_name)
                generate_alerts()
                st.success(f"✅ Updated successfully by {role_name}")
        else:
            st.error("UID not found")

    st.markdown("---")

    # --- QR Scan ---
    st.subheader("Scan QR with Camera")
    camera_image = st.camera_input(f"Take a photo of the QR code ({role_name})")
    if camera_image:
        qr_text = decode_qr_from_image(camera_image)
        if qr_text:
            st.success(f"QR Data: {qr_text}")
            uid = None
            for part in qr_text.split(";"):
                if part.startswith("UID:"):
                    uid = part.split(":")[1]
                    break

            if uid:
                prod = find_product(uid)
                if prod:
                    st.json(prod)
                    fitted = st.date_input("Fitted Date (from QR)", datetime.now().date(), key=f"fit_qr_{role_name}")
                    insp = st.date_input("Inspection Date (from QR)", datetime.now().date(), key=f"insp_qr_{role_name}")
                    if st.button(f"Save Update (QR Scan) - {role_name}"):
                        update_product(uid, str(fitted), str(insp), "Fitted")
                        complete_task(uid, user["Username"], role_name)
                        generate_alerts()
                        st.success(f"✅ Updated UID {uid} successfully by {role_name}")
                else:
                    st.error("UID not found in database")
        else:
            st.error("❌ No QR code detected in image")


# ========================
# ROLE DASHBOARDS
# ========================
def admin_panel(user):
    st.header("Admin Dashboard")
    show_inbox(user)

    # QR Generation panel (only Admin)
    materials = st.multiselect("Materials", list(material_codes.keys()), ["elastic_clip"])
    vendor_lot = st.text_input("Vendor Lot")
    batch = st.number_input("Batch", min_value=1, value=1)
    qty = st.number_input("Quantity", min_value=1, value=2)

    if st.button("Generate QRs and Print"):  # <-- changed button text
        generated = generate_qrs_bulk(materials, vendor_lot, batch, qty)
        st.success(f"Generated {len(generated)} QRs")

    assign_task_panel(user)

    if st.checkbox("Show Products"):
        view_products_panel()

def sre_panel(user):
    st.header("SRE Dashboard")
    show_inbox(user)
    view_products_panel()

def dre_panel(user):
    st.header("DRE Dashboard")
    show_inbox(user)
    view_products_panel()

def zonal_panel(user):
    st.header("Zonal Dashboard")
    show_inbox(user)
    view_products_panel()


# ========================
# APP START
# ========================
st.title("Indian Railways - Track Management Register (IR-TMR)")


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if not st.session_state.logged_in:
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = authenticate(username, password)
        if not user:
            st.error("Invalid credentials")
        else:
            st.session_state.logged_in = True
            st.session_state.user = user
            st.rerun()
else:
    user = st.session_state.user
    st.success(f"Welcome {user['Username']} ({user['Role']})")

    role = user["Role"]
    if role == "Admin":
        admin_panel(user)
    elif role == "JE":
        update_panel(user, "JE")
    elif role == "Technical":
        update_panel(user, "Technical Engineer")
    elif role == "PWI":
        update_panel(user, "PWI")
    elif role == "SRE":
        sre_panel(user)
    elif role == "DRE":
        dre_panel(user)
    elif role == "Zonal":
        zonal_panel(user)

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()
