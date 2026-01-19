# Technical Documentation

## Architecture Overview


The application follows a **Streamlit** frontend architecture with a custom **Hybrid Database Manager** backend.

Additionally, a **Companion App** is deployed as a microservice using **NiceGUI** and **FastAPI**.

### Companion App Architecture (`/dubay/2D_Mandrake/`)
*   **Framework**: NiceGUI (Vue.js wrapper) running on FastAPI.
*   **Infrastructure**: Hosted on VPS behind Nginx Reverse Proxy.
*   **Server Logic**:
    *   `main.py`: Entry point integrating FastAPI and NiceGUI via `ui.run_with(fastapi_app)`.
    *   `companion.service`: Systemd unit managing the `uvicorn` process.
    *   **Proxy Headers**: Configured to trust `X-Forwarded-Prefix: /dubay/2D_Mandrake` to ensure correct asset loading.
*   **Deployment**: Handled by `deploy_fastapi_companion.py`.

### Hybrid Database Model (`database_manager.py`)
To support field operations where internet might be intermittent, the app abstraction layer (`DatabaseManager`) handles routing queries:

1.  **Cloud Mode (Priority)**:
    *   Direct connection to MySQL Cloud via `mysql-connector-python`.
    *   **SSH Tunneling**: If `[ssh]` config is present in `secrets.toml`, the manager establishes an SSH tunnel (Port Forwarding) via `SSHTunnel` helper. This allows secure access to VPS databases (e.g., `74.208.225.182`) that block remote 3306 connections.
    *   **Port Collision & Retry**: The `SSHTunnel` class includes a 5-retry mechanism for socket binding to handle rapid application restarts or role swaps without port conflict errors.
    *   **Dynamic Role Swapping**: Users can swap **Primary** and **Secondary** cloud databases in real-time. The UI reflects the current active host (Hostek vs VPS) using dynamic labels and bypasses Streamlit's `st.secrets` cache by reading from disk.
    *   **Cloud Replication**: A built-in sync engine (`replicate_cloud_db`) allows one-click data migration between Primary and Secondary cloud nodes to ensure high availability.
2.  **Local Mode (Fallback)**:
    *   Uses `sqlite3` with a local file `local_cache.db`.
    *   **Query Translation**: The manager automatically translates MySQL-specific syntax (e.g., `%s` placeholders, `NOW()`) into SQLite-compatible syntax at runtime.
    *   **Sync**: A `_sync_data()` method pulls the latest data from Cloud to Local cache.

### Centralized User Management
While main application data (assets, tickets) can be swapped between cloud nodes, **Companion App Users** are centralized on the **Linux VPS** (`dubaytech_db`).
*   **Routing**: `DatabaseManager` uses a dedicated `_get_vps_conn` method for user operations (`get`, `add`, `delete`, `update`).
*   **Authentication**: Passwords are hashed using the **PBKDF2-SHA256** algorithm via the `passlib` library.
*   **Password Reset**: Admins can update a user's password via the `update_companion_user_password` method, which is exposed in the **Settings** UI.
*   **Rationale**: Ensures a consistent login experience for end-users even during maintenance swaps of the primary asset database.

### File Storage & Sync (`_sync_files`)
Files are managed separately from the Database to handle large blobs efficiently.
*   **Local Cache** (Primary): All files are saved to `2D_Storage/`. This ensures offline availability.
*   **Network Path** (Backup): Configurable via `app_config.json` (managed in Settings).
*   **Bidirectional Sync**: The `sync_files()` method copies missing files between Local and Network paths (`shutil.copy2`).

## Database Schema

### 1. Core Assets
*   **`assets`**: Self-referencing table defining the hierarchy.
    *   `id`, `parent_id` (FK), `name`, `type`, `description`.
    *   **Types**: Company, Category, Service, Offering, System, Sub-System, Asset, Group, Feature, Facility.

### 2. Ticketing System (formerly Change Management)
*   **`tickets`**: Replaces the old `changes` table.
    *   `id`, `asset_id` (FK), `ticket_type` (Incident, Request, etc), `title`, `description`, `status`, `priority`, `logged_by`, `created_at`, `updated_at`.
*   **`ticket_attachments`**: Stores file metadata.
    *   `id`, `ticket_id` (FK), `file_name`, `file_path`, `uploaded_at`.
    *   **Note**: `file_path` points to the *local* copy (`2D_Storage/...`).

### 3. Compliance & Hierarchy V2
The app implements a Many-to-Many relationship between Assets/Policies and Controls, and uses an expanded Hierarchy V2 schema for enterprise management.

*   **V2 Hierarchy Tables**:
    *   `kpu_business_services_level1`, `kpu_business_services_level2`: Service categorization.
    *   `kpu_technical_services`, `kpu_enterprise_assets`: Infrastructure mapping.
    *   `kpu_enterprise_software`, `kpu_enterprise_computing_machines`: Detailed inventory.
*   **ISO 27001:2022**
    *   `iso_controls`: Reference table (e.g., A.5.1, A.8.2).
    *   `asset_controls`: Linking table. Payload: `status` (Applicable/Compliant), `notes`.
*   **NIST CSF 2.0**
    *   `nist_controls`: Reference table (e.g., GV.OC-01).
    *   `asset_nist_controls`: Linking table.
    *   `policy_nist_mappings`: Links Policies (`policies` table) to NIST controls.

### 4. User Management
*   **`companion_users`**: Stored on the Linux VPS database.
    *   `id`, `username`, `password_hash` (PBKDF2-SHA256 via Passlib), `role`, `created_at`.

## Usage Guide

### Creating Tickets
*   Navigate to **Hierarchy Explorer**.
*   Select an asset or click the **"🎫 Ticket"** button.
*   Fill in the form:
    *   **Type**: Incident, Service Request, Change, Problem.
    *   **Details**: Title, Description, Priority.
    *   **Status**: Open, In Progress, etc.
*   **Attachments**: Drag & Drop files to attach them to the ticket.
*   This writes to the `tickets` and `ticket_attachments` tables.

### Managing Compliance
*   Toggle **"🛠️ Manage Mode"** in the sidebar of Hierarchy Explorer.
*   Click the **Shield Icon (🛡️)** next to an asset.
*   **Tabbed Interface**: Switch between ISO and NIST tabs to link controls.
*   **Status**: Mark controls as "Compliant", "Non-Compliant", or "Not Applicable".

### Distribution
To distribute this app:
1.  Zip the root folder (excluding `__pycache__` and `local_cache.db`).
2.  Ensure the user runs `database_setup.py` once to initialize their local environment if cloud is not used, or to seed the cloud if it is fresh.
