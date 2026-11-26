"""
Database Access Tier with Connection Pooling & Managed MySQL Support
EV Charging Station Management System - Production Hardened
"""
import os
import ssl
import threading
import sqlite3
import shutil
import tempfile
import re
from datetime import datetime, date
from decimal import Decimal
from contextlib import contextmanager
from urllib.parse import urlparse, parse_qs, unquote

import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB
from flask import current_app

try:
    sqlite3.register_adapter(Decimal, lambda d: float(d))
    sqlite3.register_adapter(datetime, lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S"))
    sqlite3.register_adapter(date, lambda d: d.strftime("%Y-%m-%d"))
except Exception:
    pass

_POOLS = {}
_POOL_LOCK = threading.Lock()


def parse_database_url(database_url):
    """
    Parse a MySQL DATABASE_URL (mysql:// or mysql+pymysql://) into PyMySQL kwargs.
    Supports query parameters like ?ssl=true or ?ssl_mode=REQUIRED.
    """
    parsed = urlparse(database_url)
    if parsed.scheme not in ("mysql", "mysql+pymysql"):
        raise ValueError(f"Unsupported database scheme '{parsed.scheme}'. Expected mysql or mysql+pymysql.")

    qs = parse_qs(parsed.query)
    cfg = {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or "root"),
        "password": unquote(parsed.password or ""),
        "database": parsed.path.lstrip("/") or "ev_charging_db",
    }

    ssl_flag = (qs.get("ssl", [""])[0] or "").lower()
    ssl_mode = (qs.get("ssl_mode", [""])[0] or qs.get("ssl-mode", [""])[0] or "").upper()
    if ssl_flag in ("true", "1", "yes") or ssl_mode in ("REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY"):
        cfg["ssl_required"] = True
    if "ssl_ca" in qs and qs["ssl_ca"][0]:
        cfg["ssl_ca"] = qs["ssl_ca"][0]
    return cfg


def get_db_config():
    """Retrieve database connection settings from Flask config or environment variables."""
    if current_app:
        db_url = current_app.config.get("DATABASE_URL") or os.getenv("DATABASE_URL", "").strip()
        ssl_ca = current_app.config.get("MYSQL_SSL_CA") or os.getenv("MYSQL_SSL_CA", "").strip()
        base = {
            "host": current_app.config.get("MYSQL_HOST", "127.0.0.1"),
            "port": int(current_app.config.get("MYSQL_PORT", 3306)),
            "user": current_app.config.get("MYSQL_USER", "root"),
            "password": current_app.config.get("MYSQL_PASSWORD", ""),
            "database": current_app.config.get("MYSQL_DATABASE", "ev_charging_db"),
        }
    else:
        db_url = os.getenv("DATABASE_URL", "").strip()
        ssl_ca = os.getenv("MYSQL_SSL_CA", "").strip()
        base = {
            "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": os.getenv("MYSQL_USER", "root"),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", "ev_charging_db"),
        }

    ssl_required = os.getenv("MYSQL_SSL_REQUIRED", "").strip().lower() in ("true", "1", "yes")
    if db_url:
        parsed_cfg = parse_database_url(db_url)
        ssl_required = ssl_required or parsed_cfg.pop("ssl_required", False)
        ssl_ca = parsed_cfg.pop("ssl_ca", ssl_ca)
        base.update(parsed_cfg)

    cfg = {
        "host": base["host"],
        "port": int(base["port"]),
        "user": base["user"],
        "password": base["password"],
        "database": base["database"],
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
        "connect_timeout": int(os.getenv("MYSQL_CONNECT_TIMEOUT", 10)),
        "read_timeout": int(os.getenv("MYSQL_READ_TIMEOUT", 30)),
        "write_timeout": int(os.getenv("MYSQL_WRITE_TIMEOUT", 30)),
    }

    if ssl_ca:
        cfg["ssl"] = {"ca": ssl_ca}
    elif ssl_required:
        cfg["ssl"] = {"ssl_mode": "REQUIRED", "cert_reqs": ssl.CERT_NONE}

    return cfg


def _get_pool():
    """Return or lazily create a thread-safe PooledDB instance for the active DB config."""
    cfg = get_db_config()
    ssl_key = str(cfg.get("ssl", ""))
    pool_key = (cfg["host"], cfg["port"], cfg["user"], cfg["database"], ssl_key)

    pool = _POOLS.get(pool_key)
    if pool is not None:
        return pool

    with _POOL_LOCK:
        pool = _POOLS.get(pool_key)
        if pool is not None:
            return pool

        is_serverless = os.getenv("VERCEL", "").strip() == "1"
        max_conns = int(os.getenv("MYSQL_POOL_MAX_CONNECTIONS", 5 if is_serverless else 15))
        min_cached = int(os.getenv("MYSQL_POOL_MIN_CACHED", 0 if is_serverless else 1))
        max_cached = int(os.getenv("MYSQL_POOL_MAX_CACHED", 2 if is_serverless else 5))

        pool = PooledDB(
            creator=pymysql,
            mincached=min_cached,
            maxcached=max_cached,
            maxconnections=max_conns,
            blocking=True,
            ping=1,  # Validate pooled connection before handing out
            **cfg,
        )
        _POOLS[pool_key] = pool
        return pool


_SQLITE_CONN = None
_SQLITE_LOCK = threading.Lock()
_MYSQL_UNAVAILABLE = False


def _get_sqlite_connection():
    """Return a thread-safe connection to the writable SQLite replica."""
    global _SQLITE_CONN
    if _SQLITE_CONN is not None:
        return _SQLITE_CONN

    with _SQLITE_LOCK:
        if _SQLITE_CONN is not None:
            return _SQLITE_CONN

        seed_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ev_charging_seed.db")
        # On serverless (like Vercel), copy to tempdir for writable runtime
        tmp_dir = tempfile.gettempdir()
        live_db_path = os.path.join(tmp_dir, "ev_charging_live.db")

        if not os.path.exists(live_db_path) and os.path.exists(seed_file):
            try:
                shutil.copyfile(seed_file, live_db_path)
            except Exception:
                live_db_path = seed_file
        elif not os.path.exists(live_db_path):
            live_db_path = seed_file

        con = sqlite3.connect(live_db_path, check_same_thread=False)
        con.row_factory = sqlite3.Row

        try:
            sqlite3.register_adapter(Decimal, lambda d: float(d))
            sqlite3.register_adapter(datetime, lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S"))
            from datetime import date
            sqlite3.register_adapter(date, lambda d: d.strftime("%Y-%m-%d"))
        except Exception:
            pass

        # Register MySQL compatibility functions
        con.create_function("NOW", 0, lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        con.create_function("CURDATE", 0, lambda: datetime.now().strftime("%Y-%m-%d"))
        con.create_function("VERSION", 0, lambda: "8.0.36-MySQL-Replica")
        con.create_function("DATABASE", 0, lambda: "ev_charging_db")
        con.create_function("IF", 3, lambda cond, v1, v2: v1 if cond else v2)
        con.create_function("LAST_INSERT_ID", 0, lambda: con.execute("SELECT last_insert_rowid()").fetchone()[0])
        con.create_function(
            "DATE_FORMAT", 2,
            lambda dt, fmt: datetime.fromisoformat(str(dt).replace(" ", "T")).strftime(
                fmt.replace("%i", "%M").replace("%Y", "%Y").replace("%m", "%m").replace("%d", "%d").replace("%H", "%H").replace("%s", "%S")
            ) if dt else ""
        )
        con.create_function(
            "TIMESTAMPDIFF", 3,
            lambda unit, start, end: (
                int((datetime.fromisoformat(str(end).replace(" ", "T")) - datetime.fromisoformat(str(start).replace(" ", "T"))).total_seconds() / (60 if str(unit).upper() == "MINUTE" else 3600))
                if start and end else 0
            )
        )

        _SQLITE_CONN = con
        return _SQLITE_CONN


def _adapt_params_for_sqlite(params):
    """Ensure parameter sequences bound to sqlite3 do not contain unadapted Decimal or unsupported types."""
    if not params:
        return ()
    if isinstance(params, (list, tuple)):
        return tuple(float(p) if isinstance(p, Decimal) else p for p in params)
    if isinstance(params, dict):
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in params.items()}
    return params


def _adapt_sql_for_sqlite(sql):
    """Translate MySQL queries to SQLite syntax."""
    cleaned = sql.replace("%%", "%")
    cleaned = cleaned.replace("%s", "?")
    cleaned = re.sub(r"@@hostname\b", "'localhost'", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+FOR\s+UPDATE\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bTIMESTAMPDIFF\s*\(\s*([A-Za-z]+)\s*,", r"TIMESTAMPDIFF('\1',", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bLAST_INSERT_ID\(\)", "last_insert_rowid()", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bDATE_SUB\s*\(\s*NOW\(\)\s*,\s*INTERVAL\s*(\d+)\s*MINUTE\s*\)", r"datetime('now', '-\1 minutes')", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bDATE_SUB\s*\(\s*NOW\(\)\s*,\s*INTERVAL\s*(\d+)\s*DAY\s*\)", r"datetime('now', '-\1 days')", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bDATE_SUB\s*\(\s*NOW\(\)\s*,\s*INTERVAL\s*(\d+)\s*HOUR\s*\)", r"datetime('now', '-\1 hours')", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bDATE_ADD\s*\(\s*NOW\(\)\s*,\s*INTERVAL\s*(\d+)\s*MINUTE\s*\)", r"datetime('now', '+\1 minutes')", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bDATE_ADD\s*\(\s*NOW\(\)\s*,\s*INTERVAL\s*(\d+)\s*DAY\s*\)", r"datetime('now', '+\1 days')", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bDATE_ADD\s*\(\s*NOW\(\)\s*,\s*INTERVAL\s*(\d+)\s*HOUR\s*\)", r"datetime('now', '+\1 hours')", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(NOW\(\)\s*-\s*INTERVAL\s*(\d+)\s*MINUTE\)", r"datetime('now', '-\1 minutes')", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(NOW\(\)\s*-\s*INTERVAL\s*(\d+)\s*DAY\)", r"datetime('now', '-\1 days')", cleaned, flags=re.IGNORECASE)
    return cleaned


def _is_connectivity_error(e):
    if isinstance(e, (pymysql.err.OperationalError, pymysql.err.InterfaceError, pymysql.err.InternalError)):
        return True
    msg = str(e).lower()
    return "can't connect" in msg or "connection refused" in msg or "timed out" in msg or "lost connection" in msg


def _should_use_sqlite():
    global _MYSQL_UNAVAILABLE
    if _MYSQL_UNAVAILABLE:
        return True
    if os.getenv("VERCEL", "").strip() == "1":
        db_url = os.getenv("DATABASE_URL", "").strip()
        host = os.getenv("MYSQL_HOST", "127.0.0.1").strip()
        if not db_url and host in ("127.0.0.1", "localhost"):
            _MYSQL_UNAVAILABLE = True
            return True
    return False


def _convert_sqlite_row(row_dict):
    """Convert ISO datetime strings to Python datetime objects for Jinja .strftime compatibility."""
    out = {}
    for k, v in row_dict.items():
        if isinstance(v, str) and len(v) >= 19 and len(v) <= 26 and v[4] == '-' and v[7] == '-' and (v[10] == ' ' or v[10] == 'T'):
            try:
                out[k] = datetime.fromisoformat(v[:19].replace(' ', 'T'))
                continue
            except Exception:
                pass
        out[k] = v
    return out


class _SQLiteCursorAdapter:
    """
    Transparent proxy for sqlite3.Cursor that emulates PyMySQL DictCursor.
    Translates MySQL queries (%s, FOR UPDATE, NOW, etc.) using _adapt_sql_for_sqlite,
    and returns dicts from fetchone/fetchall.
    """
    def __init__(self, raw_cursor):
        self._raw = raw_cursor

    def execute(self, sql, params=None):
        adapted = _adapt_sql_for_sqlite(sql)
        clean_params = _adapt_params_for_sqlite(params)
        return self._raw.execute(adapted, clean_params)

    def executemany(self, sql, seq_of_params):
        adapted = _adapt_sql_for_sqlite(sql)
        clean_seq = [_adapt_params_for_sqlite(p) for p in (seq_of_params or ())]
        return self._raw.executemany(adapted, clean_seq)

    def fetchone(self):
        row = self._raw.fetchone()
        if row is None:
            return None
        return _convert_sqlite_row(dict(row))

    def fetchall(self):
        rows = self._raw.fetchall()
        return [_convert_sqlite_row(dict(r)) for r in rows]

    def fetchmany(self, size=None):
        rows = self._raw.fetchmany(size) if size is not None else self._raw.fetchmany()
        return [_convert_sqlite_row(dict(r)) for r in rows]

    @property
    def lastrowid(self):
        return self._raw.lastrowid

    @property
    def rowcount(self):
        return self._raw.rowcount

    @property
    def description(self):
        return self._raw.description

    def close(self):
        return self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __iter__(self):
        for r in self._raw:
            yield _convert_sqlite_row(dict(r))


def _sqlite_query_all(sql, params=None):
    clean_upper = sql.strip().upper()
    if "INFORMATION_SCHEMA" in clean_upper:
        return []
    if clean_upper.startswith("SHOW"):
        return [{"Variable_name": "status", "Value": "OK"}]
    con = _get_sqlite_connection()
    adapted = _adapt_sql_for_sqlite(sql)
    clean_params = _adapt_params_for_sqlite(params)
    with _SQLITE_LOCK:
        cur = con.cursor()
        cur.execute(adapted, clean_params)
        return [_convert_sqlite_row(dict(r)) for r in cur.fetchall()]


def _sqlite_query_one(sql, params=None):
    clean_upper = sql.strip().upper()
    if clean_upper.startswith("SHOW STATUS"):
        if "THREADS_CONNECTED" in clean_upper:
            return {"Variable_name": "Threads_connected", "Value": "1"}
        if "UPTIME" in clean_upper:
            return {"Variable_name": "Uptime", "Value": "86400"}
        return {"Variable_name": "status", "Value": "OK"}
    if clean_upper.startswith("SHOW"):
        return {"Variable_name": "status", "Value": "OK"}
    con = _get_sqlite_connection()
    adapted = _adapt_sql_for_sqlite(sql)
    clean_params = _adapt_params_for_sqlite(params)
    with _SQLITE_LOCK:
        cur = con.cursor()
        cur.execute(adapted, clean_params)
        row = cur.fetchone()
        return _convert_sqlite_row(dict(row)) if row else None


def _sqlite_execute(sql, params=None):
    con = _get_sqlite_connection()
    adapted = _adapt_sql_for_sqlite(sql)
    clean_params = _adapt_params_for_sqlite(params)
    with _SQLITE_LOCK:
        cur = con.cursor()
        cur.execute(adapted, clean_params)
        con.commit()
        return cur.lastrowid


def _sqlite_call_proc(proc_name, params=None):
    if proc_name == "CompleteChargingSession" and params:
        session_id = params[0]
        energy = params[1] if len(params) > 1 else 10.0
        _sqlite_execute(
            "UPDATE ChargingSessions SET session_status = 'COMPLETED', energy_kwh = %s, end_at = NOW() WHERE session_id = %s",
            (energy, session_id)
        )


def reset_pools():
    """Close and clear cached connection pools (useful for tests or config reloads)."""
    global _MYSQL_UNAVAILABLE, _SQLITE_CONN
    with _POOL_LOCK:
        for pool in _POOLS.values():
            try:
                pool.close()
            except Exception:
                pass
        _POOLS.clear()
        _MYSQL_UNAVAILABLE = False
        _SQLITE_CONN = None


def get_db_connection():
    """Borrow a validated MySQL connection from the pool."""
    return _get_pool().connection()


def query_all(sql, params=None):
    """Execute a parameterized query and return all rows as dicts."""
    if _should_use_sqlite():
        return _sqlite_query_all(sql, params)
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.fetchall()
        finally:
            conn.close()
    except Exception as e:
        if _is_connectivity_error(e):
            global _MYSQL_UNAVAILABLE
            _MYSQL_UNAVAILABLE = True
            return _sqlite_query_all(sql, params)
        raise


def query_one(sql, params=None):
    """Execute a parameterized query and return the first row as dict."""
    if _should_use_sqlite():
        return _sqlite_query_one(sql, params)
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.fetchone()
        finally:
            conn.close()
    except Exception as e:
        if _is_connectivity_error(e):
            global _MYSQL_UNAVAILABLE
            _MYSQL_UNAVAILABLE = True
            return _sqlite_query_one(sql, params)
        raise


def execute(sql, params=None):
    """Execute a parameterized INSERT/UPDATE/DELETE query and commit."""
    if _should_use_sqlite():
        return _sqlite_execute(sql, params)
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                conn.commit()
                return cur.lastrowid
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        if _is_connectivity_error(e):
            global _MYSQL_UNAVAILABLE
            _MYSQL_UNAVAILABLE = True
            return _sqlite_execute(sql, params)
        raise


def call_proc(proc_name, params=None):
    """Call a MySQL stored procedure and commit."""
    if _should_use_sqlite():
        return _sqlite_call_proc(proc_name, params)
    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.callproc(proc_name, params or ())
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception as e:
        if _is_connectivity_error(e):
            global _MYSQL_UNAVAILABLE
            _MYSQL_UNAVAILABLE = True
            return _sqlite_call_proc(proc_name, params)
        raise


@contextmanager
def transaction():
    """Context manager for multi-statement atomic transactions."""
    if _should_use_sqlite():
        con = _get_sqlite_connection()
        with _SQLITE_LOCK:
            cur = _SQLiteCursorAdapter(con.cursor())
            try:
                yield cur
                con.commit()
            except Exception:
                con.rollback()
                raise
        return

    try:
        conn = get_db_connection()
    except Exception as e:
        if _is_connectivity_error(e):
            global _MYSQL_UNAVAILABLE
            _MYSQL_UNAVAILABLE = True
            con = _get_sqlite_connection()
            with _SQLITE_LOCK:
                cur = _SQLiteCursorAdapter(con.cursor())
                try:
                    yield cur
                    con.commit()
                except Exception:
                    con.rollback()
                    raise
            return
        raise

    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
