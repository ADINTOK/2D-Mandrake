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
        "assets",
        "kpu_component_assets",
        "kpu_enterprise_assets",
        "kpu_technical_services",
        "kpu_business_services_level2",
        "kpu_business_services_level1",
        "kpu_business_services",
        "kpu_enterprise_software",
        "kpu_enterprise_computing_machines"
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

    CREATE TABLE tickets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        asset_id INT NOT NULL,
        ticket_type VARCHAR(50), -- Incident, Service Request, Change, Problem
        title VARCHAR(255),
        description TEXT,
        status VARCHAR(50) DEFAULT 'Open', 
        priority VARCHAR(50), 
        logged_by VARCHAR(100),
        related_type VARCHAR(50) DEFAULT 'asset',
        due_date DATETIME, -- V2: SLA Due Date
        problem_id INT, -- V2: Linked Problem
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_asset_id (asset_id),
        CONSTRAINT fk_tickets_asset FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
        CONSTRAINT fk_ticket_problem FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE SET NULL
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

    # 4. ITIL V2 Tables (Knowledge Base, SLAs, Problems, Licenses, CAB)
    
    # Knowledge Base
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_articles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        content TEXT,
        category VARCHAR(100),
        tags VARCHAR(255),
        author VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)

    # SLA Policies
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sla_policies (
        id INT AUTO_INCREMENT PRIMARY KEY,
        priority VARCHAR(50) UNIQUE, -- Critical, High, Medium, Low
        response_time_minutes INT,
        resolution_time_minutes INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)
    
    # Problems (Problem Management)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS problems (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        root_cause_analysis TEXT,
        status VARCHAR(50) DEFAULT 'Open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)

    # Software Licenses
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS software_licenses (
        id INT AUTO_INCREMENT PRIMARY KEY,
        software_asset_id INT NOT NULL,
        license_key VARCHAR(255),
        vendor VARCHAR(255),
        total_seats INT DEFAULT 0,
        used_seats INT DEFAULT 0,
        expiration_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)
    
    # Change Approvals (CAB)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS change_approvals (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticket_id INT NOT NULL,
        approver_role VARCHAR(100),
        status VARCHAR(50) DEFAULT 'Pending',
        comments TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_approvals_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
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

    # Enterprise IT
    ent_id = insert_node("Enterprise IT", infra_id, "System")
    ent_sw_id = insert_node("Enterprise Software", ent_id, "Sub-System")
    insert_node("Microsoft Office 365", ent_sw_id, "Asset")
    insert_node("Billing System", ent_sw_id, "Asset")
    insert_node("CRM", ent_sw_id, "Asset")
    
    ent_hw_id = insert_node("Enterprise Hardware", ent_id, "Sub-System")
    insert_node("Employee Laptops", ent_hw_id, "Group")
    insert_node("Office Printers", ent_hw_id, "Group")

    # --- IMPORT LAYER 7 ASSETS (From CSV) ---
    print("Importing Assets from CSVs...")
    import csv

    # 1. Layer 7 Software
    csv_1 = "KPU_MasterAsset_List - Layer7List.csv"
    try:
        with open(csv_1, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader) # Skip Header
            
            count = 0
            for row in reader:
                if len(row) >= 2:
                    name = row[1].strip()
                    cat_desc = row[2].strip() if len(row) > 2 else ""
                    
                    if name:
                        insert_node(name, ent_sw_id, "Asset", description=cat_desc)
                        count += 1
            print(f"Successfully imported {count} Layer 7 Software assets.")
            
    except FileNotFoundError:
        print(f"Warning: {csv_1} not found. Skipping.")
    except Exception as e:
        print(f"Error importing {csv_1}: {e}")

    # 2. SafeList Devices (Hardware)
    csv_2 = "KPU_MasterAsset_List - SafeListDevices.csv"
    try:
        with open(csv_2, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            # Check headers or skip
            # Assuming format: User, Device Name, Model, Serial, etc. based on typical device lists
            # We'll inspect the first row to be sure, but standard DictReader might be safer if headers exist
            headers = next(reader, None)
            
            count = 0
            for row in reader:
                # Based on file inspection (User: Machine Name, Device Name)
                # Adjust index based on actual file content from next step if needed, 
                # but generically mapping col 1 or 2 is safe for now.
                # Let's map 'Device Name' (col 0 or 1) as name.
                if len(row) >= 1:
                    d_name = row[0].strip()
                    if d_name:
                         insert_node(d_name, ent_hw_id, "Asset", description="Imported Device")
                         count += 1
            print(f"Successfully imported {count} SafeList Devices.")

    except FileNotFoundError:
        print(f"Warning: {csv_2} not found. Skipping.")
    except Exception as e:
         print(f"Error importing {csv_2}: {e}")

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

    # =============================================================================
    # 2. HIERARCHY V2.0 TABLES (New Strict Schema)
    # =============================================================================
    print(" Creating Hierarchy v2.0 Tables...")
    
    # Table 1: Business Services Level 1
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kpu_business_services_level1 (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        owner VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)

    # Table 2: Business Services Level 2 (Child of Level 1)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kpu_business_services_level2 (
        id INT AUTO_INCREMENT PRIMARY KEY,
        business_service_level1_id INT,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (business_service_level1_id) REFERENCES kpu_business_services_level1(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)
    
    # Table 3: Technical Services (Child of Level 2)
    # NOTE: Was child of 'business_service' (Level 1), now child of 'level 2'
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kpu_technical_services (
        id INT AUTO_INCREMENT PRIMARY KEY,
        business_service_level2_id INT,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        sla_level VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (business_service_level2_id) REFERENCES kpu_business_services_level2(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)
    
    # Table 4: Enterprise Assets (Child of Technical Service)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kpu_enterprise_assets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        technical_service_id INT,
        name VARCHAR(255) NOT NULL,
        asset_type VARCHAR(100), -- Server, Database, Router, etc.
        location VARCHAR(100),
        status VARCHAR(50) DEFAULT 'Active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (technical_service_id) REFERENCES kpu_technical_services(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)
    
    # Table 5: Component Assets (Child of Enterprise Asset)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kpu_component_assets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        enterprise_asset_id INT,
        name VARCHAR(255) NOT NULL,
        component_type VARCHAR(100), -- Module, Agent, Disk, etc.
        version VARCHAR(50),
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (enterprise_asset_id) REFERENCES kpu_enterprise_assets(id) ON DELETE CASCADE
    ) ENGINE=InnoDB;
    """)
    
    # =============================================================================
    # 3. SEED DATA FOR V2.0
    # =============================================================================
    # Only seed if empty to prevent duplicates on re-run
    # Check Level 1 table
    cursor.execute("SELECT COUNT(*) FROM kpu_business_services_level1")
    if cursor.fetchone()[0] == 0:
        print(" Seeding Hierarchy v2.0 Data...")
        
        # 1. Business Services Level 1
        l1_data = [
            ("Corporate Operations", "Core business functions", "COO"),
            ("Finance Org", "Financial management", "CFO")
        ]
        for name, desc, owner in l1_data:
            cursor.execute("INSERT INTO kpu_business_services_level1 (name, description, owner) VALUES (%s, %s, %s)", (name, desc, owner))
            
        # Get L1 ID
        cursor.execute("SELECT id FROM kpu_business_services_level1 WHERE name='Corporate Operations'")
        l1_ops_id = cursor.fetchone()[0]
        
        # 2. Business Services Level 2
        l2_data = [
            (l1_ops_id, "Corporate Communications", "Internal messaging and email services"),
            (l1_ops_id, "Facilities Management", "Physical office management")
        ]
        for pid, name, desc in l2_data:
             cursor.execute("INSERT INTO kpu_business_services_level2 (business_service_level1_id, name, description) VALUES (%s, %s, %s)", (pid, name, desc))

        # Get L2 ID
        cursor.execute("SELECT id FROM kpu_business_services_level2 WHERE name='Corporate Communications'")
        l2_comm_id = cursor.fetchone()[0]
        
        # 3. Technical Services (Now linked to Level 2)
        ts_data = [
            (l2_comm_id, "Exchange Email Service", "Core email routing and storage", "Gold"),
            (l2_comm_id, "Teams Collaboration", "Chat and Video conferencing", "Silver")
        ]
        for pid, name, desc, sla in ts_data:
            cursor.execute("INSERT INTO kpu_technical_services (business_service_level2_id, name, description, sla_level) VALUES (%s, %s, %s, %s)", (pid, name, desc, sla))
            
        # Get IDs
        cursor.execute("SELECT id FROM kpu_technical_services WHERE name='Exchange Email Service'")
        ts_email_id = cursor.fetchone()[0]
        
        # 4. Enterprise Assets
        ea_data = [
            (ts_email_id, "EXCH-SVR-01", "Server", "NY Data Center"),
            (ts_email_id, "EXCH-SVR-02", "Server", "London Data Center"),
            (ts_email_id, "Email Gateway Appliance", "Appliance", "Cloud")
        ]
        for pid, name, atype, loc in ea_data:
            cursor.execute("INSERT INTO kpu_enterprise_assets (technical_service_id, name, asset_type, location) VALUES (%s, %s, %s, %s)", (pid, name, atype, loc))
            
        # Get IDs
        cursor.execute("SELECT id FROM kpu_enterprise_assets WHERE name='EXCH-SVR-01'")
        ea_svr_id = cursor.fetchone()[0]
        
        # 5. Component Assets
        ca_data = [
            (ea_svr_id, "Transport Agent", "Software Module", "v15.2"),
            (ea_svr_id, "C: Drive Volume", "Storage", "500GB SSD"),
            (ea_svr_id, "Network Interface Card", "Hardware", "10GbE")
        ]
        for pid, name, ctype, ver in ca_data:
            cursor.execute("INSERT INTO kpu_component_assets (enterprise_asset_id, name, component_type, version) VALUES (%s, %s, %s, %s)", (pid, name, ctype, ver))

        # 16. KPU Enterprise Software
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kpu_enterprise_software (
            id INT AUTO_INCREMENT PRIMARY KEY,
            asset_id VARCHAR(255),
            name VARCHAR(255),
            manufacturer VARCHAR(255),
            mfa_enabled VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """)

        # 17. KPU Enterprise Computing Machines
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kpu_enterprise_computing_machines (
            id INT AUTO_INCREMENT PRIMARY KEY,
            asset_id VARCHAR(255),
            name VARCHAR(255),
            ip_address VARCHAR(50),
            mac_address VARCHAR(50),
            owner VARCHAR(255),
            os_type VARCHAR(100),
            location VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB;
        """)

    conn.commit()
    print("Database Setup Complete.")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    setup_database()
