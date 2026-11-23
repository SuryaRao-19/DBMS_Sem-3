"""
Cross-Platform Database Initialization & Non-Destructive Migration Script
EV Charging Station Management System
"""
import argparse
import os
import re
import ssl
import pymysql
from dotenv import load_dotenv

load_dotenv()


def _get_connection_params(include_database=True):
    """Build PyMySQL connection parameters from DATABASE_URL or MYSQL_* env vars."""
    db_url = os.getenv("DATABASE_URL", "").strip()
    if db_url:
        from app.db import parse_database_url
        parsed = parse_database_url(db_url)
        ssl_required = parsed.pop("ssl_required", False)
        ssl_ca = parsed.pop("ssl_ca", os.getenv("MYSQL_SSL_CA", "").strip())
        params = {
            "host": parsed["host"],
            "port": int(parsed["port"]),
            "user": parsed["user"],
            "password": parsed["password"],
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": False,
        }
        if include_database:
            params["database"] = parsed["database"]
        target_db = parsed["database"]
    else:
        ssl_ca = os.getenv("MYSQL_SSL_CA", "").strip()
        ssl_required = os.getenv("MYSQL_SSL_REQUIRED", "").strip().lower() in ("true", "1", "yes")
        target_db = os.getenv("MYSQL_DATABASE", "ev_charging_db")
        params = {
            "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": os.getenv("MYSQL_USER", "root"),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": False,
        }
        if include_database:
            params["database"] = target_db

    if ssl_ca:
        params["ssl"] = {"ca": ssl_ca}
    elif ssl_required:
        params["ssl"] = {"ssl_mode": "REQUIRED", "cert_reqs": ssl.CERT_NONE}

    return params, target_db


def parse_sql_statements(sql_text, target_database=None):
    """
    Parse a MySQL script (supporting DELIMITER $$ blocks) into executable statements
    without shelling out to a platform-specific mysql binary.
    """
    delimiter = ";"
    statements = []
    buffer = []

    for raw_line in sql_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        # Rewrite hardcoded USE ev_charging_db / CREATE DATABASE when deploying to a custom DB name
        if target_database:
            if re.match(r"^USE\s+`?ev_charging_db`?\s*;?$", stripped, re.IGNORECASE):
                raw_line = f"USE `{target_database}`;"
                stripped = raw_line
            elif re.match(r"^CREATE\s+DATABASE\s+IF\s+NOT\s+EXISTS\s+`?ev_charging_db`?", stripped, re.IGNORECASE):
                raw_line = re.sub(r"ev_charging_db", f"`{target_database}`", raw_line, flags=re.IGNORECASE)
                stripped = raw_line.strip()

        delim_match = re.match(r"^DELIMITER\s+(\S+)$", stripped, re.IGNORECASE)
        if delim_match:
            if buffer:
                pending = "\n".join(buffer).strip()
                if pending:
                    statements.append(pending)
                buffer = []
            delimiter = delim_match.group(1)
            continue

        buffer.append(raw_line)
        joined = "\n".join(buffer).rstrip()
        if joined.endswith(delimiter):
            stmt = joined[:-len(delimiter)].strip()
            if stmt:
                statements.append(stmt)
            buffer = []

    leftover = "\n".join(buffer).strip()
    if leftover:
        statements.append(leftover)
    return statements


def execute_sql_file(conn, file_path, target_database):
    """Execute all statements in a SQL file using an existing PyMySQL connection."""
    with open(file_path, "r", encoding="utf-8") as fh:
        sql_text = fh.read()

    statements = parse_sql_statements(sql_text, target_database=target_database)
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()


def run_migrations(conn, db_dir, target_database):
    """Apply all ordered, non-destructive SQL migrations idempotently."""
    migrations_dir = os.path.join(db_dir, "migrations")
    files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".sql"))
    for fname in files:
        fpath = os.path.join(migrations_dir, fname)
        print(f"[*] Applying migration: {fname}")
        execute_sql_file(conn, fpath, target_database)
        print(f"[+] Migration applied: {fname}")


def init_database(mode="migrate", seed_demo=False):
    """
    Initialize or migrate the MySQL database purely via Python + PyMySQL.
    - mode='migrate': Safe non-destructive incremental migrations only (recommended for production).
    - mode='full': Applies schema, indexes, routines/triggers, and migrations; optionally seeds demo data.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_dir = os.path.join(base_dir, "database")

    conn_params, target_db = _get_connection_params(include_database=False)
    print("============================================================")
    print(f"CONNECTING TO MYSQL ({conn_params['host']}:{conn_params['port']}) -> DB '{target_db}'")
    print(f"MODE: {mode} | SEED DEMO DATA: {seed_demo}")
    print("============================================================")

    conn = pymysql.connect(**conn_params)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{target_db}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(f"USE `{target_db}`")
        conn.commit()

        if mode == "full":
            scripts = [
                ("01_schema.sql", "Core Schema Tables"),
                ("02_constraints_indexes.sql", "Constraints & Composite Indexes"),
                ("03_routines_triggers.sql", "Stored Procedures, Triggers & Functions"),
            ]
            for script_name, description in scripts:
                print(f"[*] Applying {description} ({script_name})...")
                execute_sql_file(conn, os.path.join(db_dir, script_name), target_db)
                print(f"[+] Applied {script_name}")

        run_migrations(conn, db_dir, target_db)

        if seed_demo:
            print("[*] Seeding demonstration dataset (04_demo_data.sql)...")
            execute_sql_file(conn, os.path.join(db_dir, "04_demo_data.sql"), target_db)
            print("[+] Demo data seeded.")

        with conn.cursor() as cur:
            cur.execute("SHOW TABLES;")
            tables = [list(row.values())[0] for row in cur.fetchall()]
            print("\nDATABASE VERIFICATION SUMMARY:")
            print(f"Tables present ({len(tables)}): {', '.join(tables)}")
            for t in tables:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM `{t}`;")
                print(f"  - {t}: {cur.fetchone()['cnt']} rows")

            cur.execute("SHOW PROCEDURE STATUS WHERE Db = %s;", (target_db,))
            print(f"Stored Procedures: {', '.join(r['Name'] for r in cur.fetchall())}")

            cur.execute("SHOW FUNCTION STATUS WHERE Db = %s;", (target_db,))
            print(f"Stored Functions: {', '.join(r['Name'] for r in cur.fetchall())}")

            cur.execute(f"SHOW TRIGGERS FROM `{target_db}`;")
            print(f"Triggers: {', '.join(r['Trigger'] for r in cur.fetchall())}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize or migrate EV Charging DB")
    parser.add_argument(
        "--mode",
        choices=("migrate", "full"),
        default="migrate",
        help="migrate: non-destructive migrations only (default); full: schema + indexes + routines + migrations",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Optionally seed synthetic demonstration data (dev/evaluation only)",
    )
    args = parser.parse_args()
    init_database(mode=args.mode, seed_demo=args.seed_demo)
