# ITIL & ISO 27001 Quick Guide

Welcome to the **2D Mandrake Service Management App**. This application is built upon best practices from ITIL (Information Technology Infrastructure Library) and ISO standards. Here is a quick primer to help you navigate the concepts.

## 1. ITIL Concepts (Service Management)

### 🎫 Incident vs. Problem
*   **Incident**: An unplanned interruption to a service.
    *   *Goal*: Fix it fast.
    *   *Example*: "My printer is jammed."
*   **Problem**: The underlying cause of one or more incidents.
    *   *Goal*: Find the root cause so it never happens again.
    *   *Example*: "The printer roller is worn out and keeps jamming paper." -> **Root Cause Analysis (RCA)**.

### ⏱️ Service Level Agreements (SLA)
An SLA is a commitment between the service provider (IT) and the customer.
*   **Response Time**: How fast we acknowledge the ticket.
*   **Resolution Time**: How fast we fix the issue.
*   **Breach**: When a ticket stays open past its due date. *Action: Manager notification.*

### 🔄 Change Management
Not all changes are equal.
*   **Standard Change**: Pre-authorized, low risk (e.g., Weekly Reboot).
*   **Normal Change**: Requires approval from the **CAB (Change Advisory Board)**.
*   **Emergency Change**: Must be done immediately to fix a critical failure (approvals usually retroactive or expedited).

---

## 2. ISO 27001 Concepts (Information Security)

### 🛡️ The CIA Triad
Every security control protects one of three things:
1.  **Confidentiality**: Only authorized people can see data.
2.  **Integrity**: Data is accurate and hasn't been tampered with.
3.  **Availability**: Data is accessible when needed.

### 📝 Controls (Annex A)
We map our assets to **Controls** to ensure they are secure.
*   **A.5.1 (Policies)**: Do we have rules written down?
*   **A.8.1 (Endpoint Security)**: are laptops encrypted and antivirus installed?
*   **A.9.1 (Access Control)**: Do people only have the access they need?

### ✅ Compliance Status
*   **Compliant**: The control is effectively implemented.
*   **Non-Compliant**: There is a gap or risk.
*   **Not Applicable**: This control doesn't apply to this asset.

---

## 3. Workflow in 2D Mandrake
1.  **Service Catalog**: Users request services (Laptops, Accounts).
2.  **Tickets**: If it breaks, they log an Incident.
3.  **Problems**: If it breaks often, you promote it to a Problem.
4.  **Changes**: To fix the Problem, you might need a Change Request (e.g., "Replace Server").
5.  **Assets**: Everything is tied to an Asset (Server, Software) which is monitored for **ISO Compliance**.
