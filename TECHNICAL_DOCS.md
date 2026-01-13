# Technical Documentation

## Architecture Overview

The application follows a **Streamlit** frontend architecture with a custom **Hybrid Database Manager** backend.

### Hybrid Database Model (`database_manager.py`)
To support field operations where internet might be intermittent, the app abstraction layer (`DatabaseManager`) handles routing queries:

1.  **Cloud Mode (Priority)**:
    *   Direct connection to MySQL Cloud via `mysql-connector-python`.
    *   Used when `secrets.toml` is present and connection test passes.
2.  **Local Mode (Fallback)**:
    *   Uses `sqlite3` with a local file `local_cache.db`.
    *   **Query Translation**: The manager automatically translates MySQL-specific syntax (e.g., `%s` placeholders, `NOW()`) into SQLite-compatible syntax at runtime.
    *   **Sync**: A `sync()` method performs a two-way synchronization:
        1.  **Push**: Uploads locally created tickets to the Cloud (checking for duplicates via Composite Key).
        2.  **Reconcile**: Updates local IDs to match the newly generated Cloud IDs.
        3.  **Pull**: Downloads the latest data from Cloud to Local cache.

## Database Schema

### 1. Core Assets
*   **`assets`**: Self-referencing table defining the hierarchy.
    *   `id`, `parent_id` (FK), `name`, `type`, `description`.
    *   **Types**: Company, Category, Service, Offering, System, Sub-System, Asset, Group, Feature, Facility.

### 2. Ticketing System (formerly Change Management)
*   **`tickets`**: Replaces the old `changes` table.
    *   `id`, `asset_id` (FK), `ticket_type` (Incident, Request, etc), `title`, `description`, `status`, `priority`, `logged_by`, `created_at`, `updated_at`.
*   **`ticket_attachments`**: Stores file metadata.
    *   `id`, `ticket_id` (FK), `file_name`, `file_path`.

### 3. Compliance Frameworks
The app implements a Many-to-Many relationship between Assets/Policies and Controls.

*   **ISO 27001:2022**
    *   `iso_controls`: Reference table (e.g., A.5.1, A.8.2).
    *   `asset_controls`: Linking table. Payload: `status` (Applicable/Compliant), `notes`.
*   **NIST CSF 2.0**
    *   `nist_controls`: Reference table (e.g., GV.OC-01).
    *   `asset_nist_controls`: Linking table.
    *   `policy_nist_mappings`: Links Policies (`policies` table) to NIST controls.

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
