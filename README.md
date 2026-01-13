# 2D Mandrake v2.0

A comprehensive Asset & Change Management system. This application allows for managing asset hierarchies, tracking changes/incidents, and mapping security compliance controls (ISO 27001 & NIST 2.0).

## 🌟 Key Features

*   **Asset Hierarchy Explorer**: Visualize and manage complex asset relationships (Company -> Service -> System -> Asset).
*   **Ticketing System**: Raise **Incidents**, **Service Requests**, **Changes**, and **Problems** directly linked to assets.
*   **Document Management**: Attach files (PDF, Images) to tickets, stored securely in `2D_Storage`.
*   **Compliance Manager**: Link **ISO 27001** and **NIST CSF 2.0** controls directly to assets or policies.
*   **Visual Dependency Mapping**: Auto-generate downstream dependency graphs to analyze the impact of failures.
*   **Hybrid Database**: Works seamlessly in **Online (Cloud MySQL)** or **Offline (Local SQLite)** modes with synchronization.

##  Installation & Setup

### Prerequisites

*   **OS**: Windows 10/11
*   **Python 3.10+**
*   **MySQL Database** (or use the built-in offline mode)
    *   **Network Requirements**: If using a Cloud Database (e.g., Azure MySQL, AWS RDS), ensure your firewall/network allows:
        *   **Protocol**: TCP
        *   **Port**: 3306 (Default MySQL port)
        *   **Direction**: Outbound (from App) and Inbound (to DB)
*   **Git** (for version control)
*   **Graphviz**: Recommended for dependency visualization. [Download Installer](https://graphviz.org/download/) (Add to System PATH during installation).

### 2. Initial Setup
1.  **Unzip** the application folder.
2.  **Install Python Libraries**:
    ```powershell
    pip install -r requirements.txt
    ```
3.  **Configure Database Secrets**:
    *   Open `.streamlit/secrets.toml`.
    *   Add your Cloud MySQL credentials. (If skipped, app runs in Local Mode).

### 3. Initialize Database
**⚠️ Important:** Before running the app for the first time (or to reset data), run the setup script. This creates all tables and seeds default KPU assets and compliance controls.

```powershell
python database_setup.py
```

## 🚀 How to Run

**Option A: One-Click (Windows)**
Double-click **`run_app.bat`**.

**Option B: Terminal**
```powershell
streamlit run app.py
```

## 📂 Project Structure

*   `app.py`: Main entry point and UI logic.
*   `database_manager.py`: Handles hybrid connection logic (Cloud <-> Local sync) and Schema.
*   `database_setup.py`: **Master Setup Script**. Resets DB, creates schema, and seeds initial data.
*   `pages/`: Contains specific sub-pages (Ticket History, Grid Editor).
62: *   `2D_Storage/`: Directory for storing ticket attachments.
63: *   `local_cache.db`: Local SQLite database (created automatically).
64: 
65: ## 🔄 Offline Mode & Synchronization
66: 
67: The app is designed for field operations where connectivity is unreliable.
68: 
69: 1.  **Work Offline**:
70:     *   If the Cloud DB is unreachable, the app automatically switches to **Offline Mode (Local Cache)**.
71:     *   You can continue to view assets and create tickets.
72:     *   Tickets created offline are saved to `local_cache.db`.
73: 
74: 2.  **Two-Way Sync**:
75:     *   When back online, click the **"🔄 Sync with Cloud"** button in the sidebar.
76:     *   **Push**: Your offline tickets are uploaded to the Cloud.
77:     *   **Pull**: The latest assets and tickets from the Cloud are downloaded to your device.
78: 
79: ## 🛟 Troubleshooting

*   **"Offline Mode"**: The app defaults to this if it cannot reach the Cloud MySQL server. Check your internet or Reference `secrets.toml`.
*   **Graphviz Executable Not Found**: Ensure Graphviz is installed and added to your Windows PATH.
