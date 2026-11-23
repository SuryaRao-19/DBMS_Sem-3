"""
Phase 3 Database Architecture, Pooling & Portability Tests
EV Charging Station Management System
"""
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.db import parse_database_url, get_db_connection, query_one, reset_pools
from app.services.station_service import get_all_stations
from app.services.report_service import get_system_health
from init_db import parse_sql_statements


def test_parse_database_url_with_ssl_and_encoded_password():
    """Verify DATABASE_URL parsing for managed MySQL providers."""
    cfg = parse_database_url("mysql+pymysql://avnadmin:p%40ss%23word@mysql-demo.aivencloud.com:24891/defaultdb?ssl_mode=REQUIRED")
    assert cfg["host"] == "mysql-demo.aivencloud.com"
    assert cfg["port"] == 24891
    assert cfg["user"] == "avnadmin"
    assert cfg["password"] == "p@ss#word"
    assert cfg["database"] == "defaultdb"
    assert cfg["ssl_required"] is True


def test_parse_database_url_rejects_invalid_scheme():
    """Non-MySQL database schemes must raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported database scheme"):
        parse_database_url("postgresql://user:pass@localhost:5432/mydb")


def test_connection_pool_concurrent_queries():
    """Verify connection pool safely handles concurrent read requests."""
    def _ping(i):
        row = query_one("SELECT %s AS n, DATABASE() AS db", (i,))
        return row["n"], row["db"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_ping, range(16)))

    assert len(results) == 16
    assert all(res[0] == idx and res[1] == "ev_charging_db" for idx, res in enumerate(results))


def test_connection_failure_handled_gracefully(app, monkeypatch):
    """Verify unreachable DB returns safe 500 JSON on /api/health without leaking secrets."""
    reset_pools()
    orig_port = app.config["MYSQL_PORT"]
    app.config["MYSQL_PORT"] = 59999
    monkeypatch.setenv("MYSQL_CONNECT_TIMEOUT", "1")
    try:
        client = app.test_client()
        res = client.get("/api/health")
        assert res.status_code == 500
        data = res.get_json()
        assert data["status"] == "UNHEALTHY"
        assert data["database_connected"] is False
        assert "password" not in str(data).lower()
    finally:
        app.config["MYSQL_PORT"] = orig_port
        reset_pools()


def test_get_all_stations_aggregated_counts():
    """Verify get_all_stations returns accurate dispenser counts via single JOIN query."""
    stations = get_all_stations()
    assert len(stations) >= 3
    for s in stations:
        assert "total_points" in s
        assert "available_points" in s
        assert "occupied_points" in s
        assert s["total_points"] >= s["available_points"]


def test_system_health_includes_audit_and_settings():
    """Verify get_system_health dynamically includes AuditLogs and SystemSettings."""
    health = get_system_health()
    table_names = [t["name"] for t in health["tables"]]
    assert "Users" in table_names
    assert "AuditLogs" in table_names
    assert "SystemSettings" in table_names
    assert len(health["routines"]) >= 2
    assert len(health["triggers"]) >= 2


def test_init_db_sql_parser_supports_delimiters():
    """Verify cross-platform SQL parser splits DELIMITER $$ routines properly."""
    sample_sql = """
    -- Comment line
    USE ev_charging_db;
    DROP FUNCTION IF EXISTS TestFn;
    DELIMITER $$
    CREATE FUNCTION TestFn(x INT) RETURNS INT DETERMINISTIC NO SQL
    BEGIN
        RETURN x + 1;
    END$$
    DELIMITER ;
    SELECT 1;
    """
    stmts = parse_sql_statements(sample_sql, target_database="custom_db")
    assert len(stmts) == 4
    assert stmts[0] == "USE `custom_db`"
    assert "CREATE FUNCTION TestFn" in stmts[2]
    assert stmts[3] == "SELECT 1"

