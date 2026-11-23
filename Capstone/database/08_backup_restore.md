# MYSQL WORKBENCH BACKUP & RESTORATION GUIDE
## EV Charging Station Management System — Major Upgrade 2.0
**Target Database:** `ev_charging_db` on MySQL 8.0+ (InnoDB)  
**File:** `database/08_backup_restore.md`

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
2. Ensure all tables are selected:
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
3. Optional: Check **`Include Create Schema`** if you want the backup script to create `ev_charging_db` automatically.

### Step 5: Start Export
1. Click the **Start Export** button in the lower right corner.
2. Monitor the progress bar until you see: **`Export Completed`**.

---

## 4. Step-by-Step Database Restoration via MySQL Workbench

### Step 1: Open Data Import / Restore
1. In MySQL Workbench, select **Server** -> **Data Import** (or click **Data Import/Restore** under *Management*).

### Step 2: Select Backup Source
1. Select the radio button **`Import from Self-Contained File`**.
2. Click the `...` button and navigate to your saved backup file (e.g. `ev_charging_db_backup_YYYYMMDD.sql`).

### Step 3: Select Target Schema
1. Under **Default Target Schema**, select **`ev_charging_db`** from the dropdown.
2. *Caution:* If you do not select a schema and the backup file does not contain a `USE` statement, the import will fail with error `No database selected`.

### Step 4: Start Import & Verification
1. Click **Start Import** in the lower right corner.
2. Wait for the progress log to report: **`Import Finished`**.
3. Go to the **Schemas** tab in the Navigator, right-click, and click **Refresh All**.
4. Run `database/05_verification.sql` to verify that all 9 tables, routines, and triggers restored with 100% data integrity.

---

## 5. Command-Line Alternative (Fast CLI Backup & Restore)

If you prefer using PowerShell or Command Prompt, run:

### Command-Line Backup (`mysqldump`)
```powershell
mysqldump -u root -p --routines --triggers --databases ev_charging_db > ev_charging_backup.sql
```
*(Enter your MySQL password when prompted: `shizuna`)*

### Command-Line Restore (`mysql`)
```powershell
mysql -u root -p ev_charging_db < ev_charging_backup.sql
```
*(Enter password `shizuna` to restore all tables, routines, and data instantly).*

---

## 6. How to Avoid Common Pitfalls

| Mistake | Consequence | Corrective Action |
| :--- | :--- | :--- |
| **Forgetting to check "Dump Stored Procedures and Triggers"** | The database restores without `CalculateChargingCost` or `trg_booking_before_insert`, causing session completion and booking validation to fail. | Always verify the two checkboxes in the Data Export panel before clicking Start Export. |
| **Importing into the wrong schema** | Overwrites or pollutes another database on your MySQL server. | Always check the `Default Target Schema` field in Data Import. |
| **Restoring while Flask is performing heavy writes** | Potential lock timeout or partial transaction state. | Stop the Flask development server before running a full schema restoration. |
