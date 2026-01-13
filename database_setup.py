import mysql.connector
import streamlit as st

# Configuration
# Checks if secrets are available, otherwise gracefully warns or fails
# This is crucial for Cloud Sync to work securely
if "mysql" in st.secrets:
    SECRETS = st.secrets["mysql"]
else:
    print("Error: 'mysql' section not found in st.secrets. Please configure your .streamlit/secrets.toml")
    exit(1)

def get_connection():
    """
    Establishes a connection to the configured MySQL database.
    Retries or error handling should be managed by the caller.
    """
    return mysql.connector.connect(
        host=SECRETS["host"],
        user=SECRETS["user"],
        password=SECRETS["password"],
        database=SECRETS["database"],
        port=SECRETS.get("port", 3306)
    )

def setup_database():
    """
    Main setup routine:
    1. Drops existing tables to ensure a clean slate (CAUTION: DATA LOSS).
    2. Strings together the CREATE TABLE SQL statements for Assets, Changes, Policies, and ISO/NIST controls.
    3. Seeds the database with default KPU Telecommunications hierarchy and compliance frameworks.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"Connection Failed: {e}")
        return

    print("--- Starting Database Setup ---")

    # -----------------------------------------------------
    # 1. DROP EXISTING TABLES (Reset)
    # -----------------------------------------------------
    print("Dropping existing tables...")
    # Order matters due to Foreign Keys (Child tables first)
    tables_to_drop = [
        "policy_nist_mappings",
        "asset_nist_controls",
        "asset_controls",
        "ticket_attachments",
        "tickets",
        "changes",
        "policies",
        "nist_controls",
        "iso_controls",
        "assets"
    ]
    for t in tables_to_drop:
        cursor.execute(f"DROP TABLE IF EXISTS {t}")

    # -----------------------------------------------------
    # 2. CREATE TABLES
    # -----------------------------------------------------
    print("Creating tables...")

    # Assets Table (Hierarchical Self-Reference)
    cursor.execute("""
    CREATE TABLE assets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        parent_id INT,
        name VARCHAR(255) NOT NULL,
        type VARCHAR(50),
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_assets_parent FOREIGN KEY (parent_id) REFERENCES assets(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)

    cursor.execute("""
    CREATE TABLE tickets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        asset_id INT NOT NULL,
        ticket_type VARCHAR(50), -- Incident, Service Request, Change, Problem
        title VARCHAR(255),
        description TEXT,
        status VARCHAR(50) DEFAULT 'Open', -- Open, In Progress, Resolved, Closed
        priority VARCHAR(50), -- Low, Medium, High, Critical
        logged_by VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_asset_id (asset_id),
        CONSTRAINT fk_tickets_asset FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)

    # Attachments Table
    cursor.execute("""
    CREATE TABLE ticket_attachments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticket_id INT NOT NULL,
        file_name VARCHAR(255),
        file_path VARCHAR(500),
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_attachments_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)

    # Policies Table (Organizational Docs)
    cursor.execute("""
    CREATE TABLE policies (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        category VARCHAR(100),
        summary TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)

    # ISO Controls Master List
    cursor.execute("""
    CREATE TABLE iso_controls (
        id VARCHAR(10) PRIMARY KEY, -- e.g. 'A.5.1'
        theme VARCHAR(50), -- Organizational, People, Physical, Technological
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)

    # NIST Controls Master List
    cursor.execute("""
    CREATE TABLE nist_controls (
        id VARCHAR(10) PRIMARY KEY, -- e.g. 'GV.OC-01'
        function VARCHAR(50), -- Govern, Identify, Protect, Detect, Respond, Recover
        category VARCHAR(100), -- Organizational Context, Risk Management Strategy, etc.
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)

    # Mappings: Asset <-> ISO (Many-to-Many)
    cursor.execute("""
    CREATE TABLE asset_controls (
        id INT AUTO_INCREMENT PRIMARY KEY,
        asset_id INT NOT NULL,
        control_id VARCHAR(10) NOT NULL,
        status VARCHAR(50) DEFAULT 'Not Applicable',
        notes TEXT,
        linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
        FOREIGN KEY (control_id) REFERENCES iso_controls(id) ON DELETE CASCADE,
        UNIQUE KEY unique_link (asset_id, control_id)
    ) ENGINE=InnoDB;
    """)

    # Mappings: Asset <-> NIST (Many-to-Many)
    cursor.execute("""
    CREATE TABLE asset_nist_controls (
        id INT AUTO_INCREMENT PRIMARY KEY,
        asset_id INT NOT NULL,
        control_id VARCHAR(10) NOT NULL,
        status VARCHAR(50) DEFAULT 'Not Applicable',
        notes TEXT,
        linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
        FOREIGN KEY (control_id) REFERENCES nist_controls(id) ON DELETE CASCADE,
        UNIQUE KEY unique_nist_link (asset_id, control_id)
    ) ENGINE=InnoDB;
    """)

    # Mappings: Policy <-> NIST (Many-to-Many)
    cursor.execute("""
    CREATE TABLE policy_nist_mappings (
        policy_id INT,
        nist_control_id VARCHAR(10),
        PRIMARY KEY (policy_id, nist_control_id),
        FOREIGN KEY (policy_id) REFERENCES policies(id) ON DELETE CASCADE,
        FOREIGN KEY (nist_control_id) REFERENCES nist_controls(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)

    conn.commit()

    # -----------------------------------------------------
    # 3. SEED DATA (KPU Default Assets)
    # -----------------------------------------------------
    # This section pre-populates the database with a standard hierarchy
    # for a telecommunications company (KPU).
    
    # --- SEED ASSETS ---
    print("Seeding Assets...")
    def insert_node(name, parent_id, node_type, description=""):
        """Helper to insert an asset node and return its ID for parenting."""
        cursor.execute(
            "INSERT INTO assets (name, parent_id, type, description) VALUES (%s, %s, %s, %s)",
            (name, parent_id, node_type, description)
        )
        return cursor.lastrowid

    # Root
    root_id = insert_node("KPU Telecommunications", None, "Company")

    # Res Services
    res_id = insert_node("Residential Services", root_id, "Category")
    res_net_id = insert_node("Internet Service", res_id, "Service")
    insert_node("Fiber Optic Broadband", res_net_id, "Offering", "Symmetric high-speed plans")
    insert_node("Cable Internet", res_net_id, "Offering", "Alternative where fiber not available")
    insert_node("Managed WiFi", res_net_id, "Offering", "Routers and whole-home coverage")
    insert_node("Affordable Connectivity Program", res_net_id, "Offering")

    res_voice_id = insert_node("Voice Service", res_id, "Service")
    res_phone_id = insert_node("Basic Phone Line", res_voice_id, "Offering")
    for feat in ["Caller ID", "Call Waiting", "Call Forwarding", "Three-Way Calling", "Voice Mail"]:
        insert_node(feat, res_phone_id, "Feature")

    res_tv_id = insert_node("Television Service", res_id, "Service")
    insert_node("Cable TV Packages", res_tv_id, "Offering")
    insert_node("Local Channels & On-Demand", res_tv_id, "Offering", "Includes KPUTv+")
    insert_node("Streaming Integration", res_tv_id, "Offering")

    # Bus Services
    bus_id = insert_node("Business Services", root_id, "Category")
    bus_net_id = insert_node("Internet Service", bus_id, "Service")
    insert_node("Dedicated Fiber Optic", bus_net_id, "Offering", "Symmetric, unlimited")
    insert_node("Hosted Business Solutions", bus_net_id, "Offering", "Data center backup")

    bus_voice_id = insert_node("Voice Service", bus_id, "Service")
    insert_node("Business Phone Lines", bus_voice_id, "Offering")
    insert_node("Hosted VoIP", bus_voice_id, "Offering", "Advanced phone systems")

    bus_add_id = insert_node("Additional Business Solutions", bus_id, "Service")
    insert_node("Wireless Internet Options", bus_add_id, "Offering")
    insert_node("Security Cameras & Monitoring", bus_add_id, "Offering")
    insert_node("Custom Telecom Services", bus_add_id, "Offering", "Server backup, productivity tools")

    # Infrastructure
    infra_id = insert_node("KPU Infrastructure Assets", None, "Category", "Technical Asset Hierarchy")
    
    # Network Infra
    core_net_id = insert_node("Network Infrastructure", infra_id, "System")
    cn_id = insert_node("Core Network", core_net_id, "Sub-System")
    insert_node("Headend/Central Office", cn_id, "Facility", "Main facility in Ketchikan")
    insert_node("Core Routers & Switches", cn_id, "Asset")
    insert_node("Optical Line Terminal (OLT)", cn_id, "Asset")
    insert_node("Servers & Data Center HW", cn_id, "Asset")
    insert_node("Backup Power Systems", cn_id, "Asset", "Generators, batteries")

    trans_id = insert_node("Transport/Backbone Network", core_net_id, "Sub-System")
    insert_node("Fiber Optic Cables (Trunk)", trans_id, "Asset", "Underground/aerial ducts")
    insert_node("Fiber Strands & Splices", trans_id, "Asset")
    insert_node("Manholes & Vaults", trans_id, "Asset")
    insert_node("Submarine Cables", trans_id, "Asset")

    # Distribution
    dist_id = insert_node("Distribution Network", infra_id, "System")
    osp_id = insert_node("Plant (OSP)", dist_id, "Sub-System")
    insert_node("Fiber Distribution Hubs (FDH)", osp_id, "Asset")
    insert_node("Poles & Aerial Infra", osp_id, "Asset")
    insert_node("Underground Conduits", osp_id, "Asset")
    insert_node("Splitters & Dist Points", osp_id, "Asset")

    # Access
    acc_id = insert_node("Access Network", infra_id, "System")
    insert_node("Outside Fiber Drops", acc_id, "Asset", "To Premises")
    insert_node("Optical Network Terminals (ONT)", acc_id, "Asset", "At customer site")

    # CPE
    cpe_id = insert_node("Customer Premises Equipment (CPE)", acc_id, "Sub-System")
    rcpe_id = insert_node("Residential CPE", cpe_id, "Group")
    insert_node("Modems/Routers", rcpe_id, "Asset", "Managed WiFi")
    insert_node("Set-Top Boxes", rcpe_id, "Asset")
    insert_node("Phone Adapters", rcpe_id, "Asset", "VoIP/Landline")

    bcpe_id = insert_node("Business CPE", cpe_id, "Group")
    insert_node("Dedicated Routers/Switches", bcpe_id, "Asset")
    insert_node("IP Phones & PBX", bcpe_id, "Asset")
    insert_node("Security Cameras (CPE)", bcpe_id, "Asset")

    # Support
    supp_id = insert_node("Support Assets", infra_id, "System")
    insert_node("Vehicles & Tools", supp_id, "Group", "Field technician fleet")
    insert_node("Test Equipment", supp_id, "Group", "OTDR, etc.")
    insert_node("Spare Parts Inventory", supp_id, "Group", "Cables, connectors")

    # --- SEED ISO CONTROLS (Common subset) ---
    print("Seeding ISO 27001 Controls...")
    # Subset of ISO controls to get started
    iso_controls = [
        ("A.5.1", "Organizational", "Policies for information security"),
        ("A.5.8", "Organizational", "Information security in project management"),
        ("A.6.1", "People", "Screening"),
        ("A.7.1", "Physical", "Physical security perimeters"),
        ("A.8.1", "Technological", "User endpoint devices"),
        ("A.8.5", "Technological", "Secure authentication"),
        ("A.8.15", "Technological", "Logging"),
        ("A.8.20", "Technological", "Networks security")
    ]
    cursor.executemany("INSERT INTO iso_controls (id, theme, description) VALUES (%s, %s, %s)", iso_controls)

    # --- SEED NIST CONTROLS (Common subset) ---
    print("Seeding NIST CSF 2.0 Controls...")
    # Subset of NIST controls to get started
    nist_controls = [
        ("GV.OC-01", "Govern", "Organizational Context", "Organizational mission, objectives, and high-level priorities are understood."),
        ("GV.PO-01", "Govern", "Policy", "Organizational cybersecurity policies are established, communicated, and enforced."),
        ("ID.AM-01", "Identify", "Asset Management", "Hardware, software, and services are inventoried."),
        ("PR.AA-01", "Protect", "Identity Management", "Identities and credentials are managed."),
        ("PR.DS-01", "Protect", "Data Security", "Data-at-rest is protected."),
        ("DE.CM-01", "Detect", "Continuous Monitoring", "The network is monitored to detect potential cybersecurity events."),
        ("RS.MA-01", "Respond", "Incident Management", "Incidents are triaged and prioritized."),
        ("RC.RP-01", "Recover", "Incident Recovery", "Recovery plan is executed.")
    ]
    cursor.executemany("INSERT INTO nist_controls (id, function, category, description) VALUES (%s, %s, %s, %s)", nist_controls)

    conn.commit()
    print("Database Setup Complete.")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    setup_database()
