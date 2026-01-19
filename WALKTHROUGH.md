# Walkthrough: Advanced ITIL Features

We have upgraded **2D Mandrake** with enterprise-grade Service Management capabilities.

## 1. 📚 Knowledge Base (KB)
**Location**: Sidebar > `📚 Knowledge Base`
*   **Search**: Full-text search for existing solutions.
*   **Create**: Use the "Create New Article" expander to publish Markdown-formatted guides.
*   **Use Case**: Document recurring fixes ("Shift Left").

## 2. ⏱️ SLA Management
**Location**: `📊 Ticket Dashboard`
*   **Logic**: Every new ticket gets a `Due Date` based on Priority:
    *   **Critical**: 4 Hours
    *   **High**: 8 Hours
    *   **Medium**: 24 Hours
    *   **Low**: 3 Days
*   **Breach Warning**: In the "Global Ticket List", any Open ticket past its due date is flagged with a **Red** background and a ⚠️ warning.

## 3. 🚧 Problem Management
**Location**: `Ticket Dashboard` > Tab: `Problem Management`
*   **RCA**: Create "Problem Records" to track the Root Cause of multiple related incidents.
*   **Example**: IF 5 users report "Slow Wifi", create 1 Problem Record ("Wifi Access Point Failure") and link the incidents.

## 4. 👨‍⚖️ CAB Workbench (Change Mgmt)
**Location**: `Ticket Dashboard` > Tab: `CAB Workbench`
*   **Approval Workflow**: View all tickets of type `Change`.
*   **Actions**:
    *   ✅ **Approve**: Sets status to "Approved".
    *   ❌ **Reject**: Sets status to "Rejected".

## 5. 💳 Software Licensing
**Location**: `Enterprise Software` > Tab: `License Management`
*   **Tracking**: Add license keys and track "Used vs Total" seats with a visual progress bar.
*   **Expiry Alerts**:
    *   🟢 Valid
    *   🟡 Expiring (< 30 Days)
    *   🔴 Expired

## 7. 🌩️ Cloud High-Availability
**Location**: Sidebar > `⚙️ Settings`
*   **SSH Tunneling**: Automatically establishes a secure port-forward to the VPS database if configured. Includes retry logic for connection stability.
*   **Role Swapping**: Instantly switch the app between **Primary (Hostek)** and **Secondary (VPS)** databases.
*   **Cloud Replication**: Port data between cloud nodes with a single click in the Settings menu.

## 8. 👤 Centralized User Management
**Location**: `Settings` > `👥 Companion App Users`
*   **VPS Persistence**: User accounts for the Companion Portal are stored permanently on the Linux VPS.
*   **Self-Service Support**: Admins can now **Reset Passwords** for portal users without manually editing the database.
