# Indian Railways - Track Management Register (IR-TMR)

🚉 A QR-code based railway material tracking and management system.  
This project was built for **Smart India Hackathon 2025**.

## Features
- Role-based login (Admin, JE, Technical Engineer, PWI, SRE, DRE, Zonal)
- Admin: Bulk generate UIDs + QRs
- JE / Technical / PWI: Update fitted date (once) + inspection dates
- SRE: AI alerts for near-expiry
- DRE: Escalation management
- Zonal Officer: Complete system overview
- QR code tamper-proof integration with fallback **human-readable UID**

## Tech Stack
- Python
- Streamlit (UI)
- Pandas (data storage in CSV)
- QRCode & Pyzbar (QR generation and scanning)
- Deployed on Streamlit Cloud

## How to Run Locally
```bash
git clone https://github.com/<your-username>/IR-TMR.git
cd IR-TMR
pip install -r requirements.txt
streamlit run app.py

