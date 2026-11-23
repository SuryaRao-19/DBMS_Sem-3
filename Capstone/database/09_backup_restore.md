# MYSQL WORKBENCH BACKUP & RESTORATION GUIDE
## EV Charging Station Management System — Major Upgrade 2.0
**Target Database:** `ev_charging_db` on MySQL 8.0+ (InnoDB)  
**File:** `database/09_backup_restore.md`

---

## 1. Core Architecture Concept & Responsibilities

Before performing backups or restores, understand the distinct components:

| Component | Responsibility | Running Port / Location |
| :--- | :--- | :--- |
| **MySQL Server** | Database engine storing tables, constraints, routines, and executing SQL. | `127.0.0.1:3306` (Local service `MySQL80`) |
| **MySQL Workbench** | Visual GUI administration client for writing SQL, exporting, and managing schemas. | Desktop application |
| **Flask Backend** | Application server running Python services, handling HTTP requests, and communicating with MySQL via PyMySQL. | `http://127.0.0.1:5000` |
| **Web Frontend** | Browser interface rendering HTML5/CSS3 templates for drivers and administrators. | Chrome / Edge / Firefox |

> [!IMPORTANT]
> **MySQL Server MUST be running** for both MySQL Workbench and the Flask backend to operate. If MySQL Server is stopped, both Workbench and Flask will return connection errors.

---

## 2. Recommended Backup Strategy for Students & Evaluators

1. **Before Any Schema Modification or Migration:** Always take a full export of `ev_charging_db` before running migration scripts or altering tables.
2. **Before Demonstration / Viva:** Create a known-good snapshot (`ev_charging_db_demo_snapshot.sql`) so you can restore to a pristine state in seconds if an unexpected test corrupts data.
3. **Include Routines and Triggers:** Default exports often exclude stored procedures and triggers unless explicitly checked. Always ensure routines and triggers are enabled during export!

---

## 3. Step-by-Step Database Export via MySQL Workbench

### Step 1: Open Data Export
1. Launch **MySQL Workbench** and connect to your local MySQL instance (`root@127.0.0.1:3306`).
2. In the top menu bar, select **Server** -> **Data Export** (or click **Data Export** in the left-hand *Navigator* panel under *Management*).

### Step 2: Select Schema and Tables
1. In the **Tables to Export** pane, check the checkbox for **`ev_charging_db`**.
2. Ensure all 9 tables are selected:
   * `Users`
   * `Vehicles`
   * `Stations`
   * `ChargingPoints`
   * `Bookings`
   * `ChargingSessions`
   * `Payments`
   * `AuditLogs`
   * `SystemSettings`
3. In the dropdown beneath the table list, choose **`Dump Structure and Data`**.

### Step 3: CRITICAL: Include Routines, Events, and Triggers
On the right-hand side of the Data Export screen, check these boxes:
* [x] **Dump Stored Procedures and Functions** (Exports `CalculateChargingCost` and `CompleteChargingSession`).
* [x] **Dump Triggers** (Exports `trg_booking_before_insert` and `trg_session_before_insert`).

### Step 4: Export Options & Output Path
1. Under **Export Options**, choose **`Export to Self-Contained File`**.
2. Click the `...` button to choose a target location and name your backup, for example:
   `c:\Users\Surya Rao\Desktop\DBCAP\database\backups\ev_charging_db_backup_YYYYMMDD.sql`
3. Click the **Start Export** button in the bottom right corner.
4. Wait for the export progress bar to reach 100% ("Export completed successfully").

---

## 4. Step-by-Step Database Restoration via MySQL Workbench

### Step 1: Open Data Import
1. In MySQL Workbench, select **Server** -> **Data Import** (or click **Data Import/Restore** under *Management*).

### Step 2: Select Source File
1. Choose **`Import from Self-Contained File`**.
2. Browse and select your `.sql` backup file.

### Step 3: Select Target Schema (Safety Check)
1. In the **Default Target Schema** dropdown, select **`ev_charging_db`** (or create a new test schema like `ev_charging_db_test` to verify without overwriting production).
2. > [!CAUTION]
   > Never restore into an unintended schema! Always verify that the target schema name is exact before starting the import.

### Step 4: Start Import & Verification
1. Click the **Start Import** button.
2. Wait for the import to finish.
3. Open a new SQL tab in Workbench and run the verification queries from `database/05_verification.sql` and `database/08_data_quality_checks.sql` to confirm that all records and triggers restored with 100% fidelity.

---

## 5. Command-Line Fast Backup & Restore (Alternative)

For automated scripts or fast terminal usage, use `mysqldump` and `mysql`:

### Fast Backup Command:
```powershell
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -u root -p --routines --triggers --single-transaction ev_charging_db > database/ev_charging_db_backup.sql
```

### Fast Restore Command:
```powershell
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u root -p ev_charging_db < database/ev_charging_db_backup.sql
```
