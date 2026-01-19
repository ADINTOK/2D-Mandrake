# 2D Mandrake v2.0

A comprehensive Asset & Change Management system. This application allows for managing asset hierarchies, tracking changes/incidents, and mapping security compliance controls (ISO 27001 & NIST 2.0).

## 🌟 Key Features


*   **Asset Hierarchy Explorer**: Visualize and manage complex asset relationships (Company -> Service -> System -> Asset).
*   **Companion App (Client Portal)**: A secure, web-based portal for end-users to submit tickets and view system status.
    *   **Authentication**: Secure Login required.
    *   **User Management**: Managed via VPS Database for consistency.
*   **Ticketing System**: Raise **Incidents**, **Service Requests**, **Changes**, and **Problems** directly linked to assets.
*   **Compliance & Hierarchy V2**: Mapping **ISO 27001**, **NIST CSF 2.0**, and advanced Enterprise Assets.
*   **SSH Tunneling**: Secure access to VPS databases via automated port forwarding.
*   **High Availability**: One-click **Swap Roles** to switch between Primary and Secondary cloud nodes.
*   **Hybrid Database**: Works in **Online (Cloud MySQL)** or **Offline (Local SQLite)** modes with synchronization.

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
*   `2D_Storage/`: Directory for storing ticket attachments.
*   `local_cache.db`: Local SQLite database (created automatically).

## 🔄 Offline Mode & Synchronization

The app is designed for field operations where connectivity is unreliable.

1.  **Work Offline**:
    *   If the Cloud DB is unreachable, the app automatically switches to **Offline Mode (Local Cache)**.
    *   You can continue to view assets and create tickets.
    *   Tickets created offline are saved to `local_cache.db`.

2.  **Two-Way Cloud Sync**:
    *   When back online, click the **"🔄 Sync Cloud DB"** button in the sidebar.
    *   **Push**: Your offline tickets are uploaded to the Cloud.
    *   **Pull**: The latest assets from the Cloud are downloaded.

3.  **File Synchronization (Local ↔ Network)**:
    *   Configure a **Network / Shared Path** in `Settings` > `File Storage`.
    *   Use the **"📂 Sync Files (Net)"** button in the sidebar to synchronize attachments between your local cache and the network share.
    *   Ensures you have access to files even when the network is down (via Local Cache).

## 🌍 Companion App (Support Portal)

A standalone web portal for end-users updates.

*   **URL**: `/dubay/2D_Mandrake/`
*   **Features**:
    *   **Secure Access**: User Authentication required.
    *   **Live Status**: View real-time system health.
    *   **Submit Tickets**: Simple form for reporting issues.
    *   **Knowledge Base**: Read-only view of helpful articles.
*   **Tech Stack**: Python (NiceGUI + FastAPI), running on the same VPS.
*   **Administration**:
    *   Go to **Settings (Page 99)** in the main 2D Mandrake app.
    *   Look for **👥 Companion App Users**.
    *   **Features**: Add/Remove users and **🔑 Reset Passwords** directly from the UI.
*   **Deployment**:
    Managed via the `2D_Linux_Wizard` logic or manually:
    ```powershell
    python deploy_fastapi_companion.py
    ```

## 🛟 Troubleshooting

*   **"Offline Mode"**: The app defaults to this if it cannot reach the Cloud MySQL server. Check your internet or Reference `secrets.toml`.
*   **Graphviz Executable Not Found**: Ensure Graphviz is installed and added to your Windows PATH.
*   **Port Collision**: If swapping roles rapidly, the app may show a port error. Wait 2 seconds and retry; the `SSHTunnel` helper has built-in retry logic.
