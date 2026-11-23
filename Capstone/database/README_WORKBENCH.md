# MYSQL WORKBENCH MASTER USER GUIDE
## EV Charging Station Management System — Major Upgrade 2.0
**Target Database:** `ev_charging_db` on MySQL 8.0+ (InnoDB)  
**File:** `database/README_WORKBENCH.md`

---

## 1. Introduction

This guide walks you through operating, inspecting, and managing the **EV Charging Station Management System** database using **MySQL Workbench**. Every feature on the Flask website connects to this exact database.

### Core Database Information
* **Host:** `127.0.0.1` (localhost)
* **Port:** `3306`
* **Database Name:** `ev_charging_db`
* **Default Admin User:** `root`
* **Default Database Password:** `shizuna` (or your configured local MySQL password)

---

## 2. Connecting to MySQL in Workbench

1. Launch the **MySQL Workbench** desktop application.
2. Under **MySQL Connections**, click on **Local instance MySQL80** (or click the `+` icon to add a new connection with Host: `127.0.0.1`, Port: `3306`, Username: `root`).
3. Enter your MySQL password (`shizuna`).
4. You will see the main workbench interface with the **Navigator** on the left and a central SQL editor.

---

## 3. Directory File Organization & Execution Order

The `database/` folder is structured into numbered scripts. Execute them in this sequence:

```
database/
├── 01_schema.sql                  (1. Creates DB and all 9 normalized tables safely)
├── 02_constraints_indexes.sql     (2. Applies composite B-Tree indexes & constraints)
├── 03_routines_triggers.sql       (3. Deploys stored procedures, functions, & triggers)
├── 04_demo_data.sql               (4. Inserts realistic synthetic demonstration data)
├── 05_verification.sql            (5. Automated tests checking integrity & routines)
├── 06_reports.sql                 (6. Analytical reporting queries & EXPLAIN plans)
├── 07_admin_queries.sql           (7. Inspection, transaction templates, & diagnostics)
├── 08_data_quality_checks.sql     (8. Exhaustive 10-point data quality & integrity audit)
├── 09_backup_restore.md           (9. Step-by-step backup and restoration instructions)
├── migrations/                    (10. Ordered, versioned schema migrations)
│   ├── 001_initial_schema.sql
│   └── 002_add_audit_logs_and_settings.sql
├── 10_roles_permissions.sql       (11. Least-privilege MySQL role definitions)
├── reset_database_DEV_ONLY.sql    (DESTRUCTIVE: Clean reset script with warnings)
├── ev_charging_db.sql             (Master 1-Click consolidated setup script)
└── README_WORKBENCH.md            (This user manual)
```

> [!TIP]
> For a **fast 1-click initial setup**, open and execute **`database/ev_charging_db.sql`**, which consolidates the entire schema, routines, triggers, indexes, and demo data in one script!


---

## 4. How to Open and Execute SQL Scripts

1. In MySQL Workbench, click **File** -> **Open SQL Script...** (or press `Ctrl + Shift + O`).
2. Navigate to the `database/` directory and select your desired file (e.g. `01_schema.sql`).
3. To execute the script:
   * **Execute Entire Script:** Click the **Lightning Bolt** icon without the cursor (or press `Ctrl + Shift + Enter`).
   * **Execute Single Statement:** Place your cursor on the specific SQL line and click the **Lightning Bolt with Cursor** icon (or press `Ctrl + Enter`).
4. Look at the **Action Output** pane at the bottom:
   * Green checkmarks (`✓`) indicate successful execution.
   * Red crosses (`✗`) indicate an error with an explanation and line number.

---

## 5. How to Inspect Tables and Records Visually

1. In the left-hand **Navigator** panel, click the **Schemas** tab.
2. If `ev_charging_db` is not listed, right-click any blank space and select **Refresh All**.
3. Expand **`ev_charging_db`** -> **Tables**.
4. Hover your mouse over any table (e.g. `Bookings`) and click the small **Table Icon** on the right.
5. MySQL Workbench will automatically run `SELECT * FROM ev_charging_db.Bookings LIMIT 1000;` and render the rows in an interactive **Result Grid**.

---

## 6. How to Verify Website and Workbench Use the Same Database

To prove that the Flask web application and MySQL Workbench are operating on the identical database instance:

1. **Website Action:** Open your browser to `http://127.0.0.1:5000/login`, log in as driver `aarav@example.com` / `Owner@123`, and register a new vehicle (e.g. `TEST-WB-9999`, Make: `Tesla`, Model: `Model 3`).
2. **Workbench Verification:** In MySQL Workbench, run:
   ```sql
   SELECT * FROM ev_charging_db.Vehicles WHERE registration_no = 'TEST-WB-9999';
   ```
   You will see the vehicle immediately appears with the exact user ID!
3. **Workbench Action:** In MySQL Workbench, update the battery capacity:
   ```sql
   UPDATE ev_charging_db.Vehicles SET battery_capacity_kwh = 75.00 WHERE registration_no = 'TEST-WB-9999';
   ```
4. **Website Verification:** Refresh the browser page at `http://127.0.0.1:5000/owner/vehicles`. You will see the battery capacity updated to `75.0 kWh` in real time!
5. **Clean up:** Delete the test vehicle from the website or via Workbench:
   ```sql
   DELETE FROM ev_charging_db.Vehicles WHERE registration_no = 'TEST-WB-9999';
   ```

---

## 7. Troubleshooting Common MySQL Workbench Errors

| Error Code | Error Message | Solution |
| :--- | :--- | :--- |
| **Error 1045** | `Access denied for user 'root'@'localhost'` | Check your password in `.env` and Workbench connection settings (`shizuna`). |
| **Error 1046** | `No database selected` | Double-click `ev_charging_db` in the Schemas panel or execute `USE ev_charging_db;`. |
| **Error 1146** | `Table 'ev_charging_db.XYZ' doesn't exist` | Run `database/01_schema.sql` or `ev_charging_db.sql` to instantiate the schema. |
| **Error 1451 / 1452** | `Cannot delete or update a parent row: a foreign key constraint fails` | You attempted to delete a record referenced by another table. Follow the correct dependency order. |
| **Error 1644 (SQLSTATE 45000)** | `Overlapping booking already exists` / `Vehicle does not belong to this user` | The custom trigger (`trg_booking_before_insert`) successfully blocked an invalid or conflicting operation. |
