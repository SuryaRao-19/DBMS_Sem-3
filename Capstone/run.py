"""
Application Server Entrypoint (Local Development & WSGI Target)
EV Charging Station Management System
"""
import os
import sys

# Ensure UTF-8 output encoding on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    is_prod = (
        os.getenv("FLASK_ENV", "development").strip().lower() == "production"
        or os.getenv("VERCEL", "").strip() == "1"
    )
    debug = False if is_prod else (os.getenv("FLASK_DEBUG", "False").strip().lower() in ("true", "1", "yes"))
    print("============================================================")
    print("EV CHARGING STATION MANAGEMENT SYSTEM SERVER STARTED")
    print(f"URL: http://127.0.0.1:{port} (debug={debug})")
    print("============================================================")
    app.run(host="127.0.0.1", port=port, debug=debug, use_reloader=False)
