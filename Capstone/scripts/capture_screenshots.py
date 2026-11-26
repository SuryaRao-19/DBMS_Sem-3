import os
import sys
import time
import threading

sys.path.insert(0, os.path.abspath("."))
from playwright.sync_api import sync_playwright
from app import create_app

def run_capture():
    app = create_app()
    port = 5005
    server = threading.Thread(target=lambda: app.run(port=port, use_reloader=False, debug=False), daemon=True)
    server.start()
    time.sleep(2)

    out_dirs = [
        os.path.abspath("screenshots"),
        r"C:\Users\Surya Rao\.gemini\antigravity\brain\ec3f65f3-4c59-4acd-831a-81d05de39357"
    ]
    for d in out_dirs:
        os.makedirs(d, exist_ok=True)

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    base_url = f"http://127.0.0.1:{port}"

    def save_shot(page, filename):
        for d in out_dirs:
            p = os.path.join(d, filename)
            page.screenshot(path=p, full_page=False)
        print(f"  -> Saved {filename}")

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # 1. Public Landing
        print("Capturing Public Landing Page...")
        page.goto(f"{base_url}/", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "hero_landing_full.png")

        # 2. Admin Login & Pages
        print("Logging in as Administrator (admin@evdemo.com)...")
        page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        page.fill("input[name='email']", "admin@evdemo.com")
        page.fill("input[name='password']", "Admin@123")
        page.click("button[type='submit']")
        time.sleep(1.5)

        print("Capturing Admin Dashboard...")
        save_shot(page, "admin_dashboard_full.png")

        print("Capturing Admin Stations...")
        page.goto(f"{base_url}/admin/stations", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "admin_stations_full.png")

        print("Capturing Admin Reports...")
        page.goto(f"{base_url}/admin/reports", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "admin_reports_full.png")

        print("Capturing Admin Payments Ledger...")
        page.goto(f"{base_url}/admin/payments", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "admin_payments_full.png")

        # Logout Admin
        page.goto(f"{base_url}/logout", wait_until="domcontentloaded")
        time.sleep(0.5)

        # 3. Customer Login & Pages
        print("Logging in as EV Driver / Customer (aarav@example.com)...")
        page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        page.fill("input[name='email']", "aarav@example.com")
        page.fill("input[name='password']", "Owner@123")
        page.click("button[type='submit']")
        time.sleep(1.5)

        print("Capturing Customer Mobility Dashboard...")
        save_shot(page, "customer_dashboard_full.png")

        print("Capturing Customer Stations...")
        page.goto(f"{base_url}/customer/stations", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "customer_stations_full.png")

        print("Capturing Customer Vehicles...")
        page.goto(f"{base_url}/customer/vehicles", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "customer_vehicles_full.png")

        print("Capturing Customer Bookings...")
        page.goto(f"{base_url}/customer/bookings", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "customer_bookings_full.png")

        print("Capturing Customer Active Charging Simulator...")
        page.goto(f"{base_url}/customer/charging", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "customer_charging_full.png")

        print("Capturing Customer Payments & Reservation Wizard...")
        page.goto(f"{base_url}/customer/payments", wait_until="domcontentloaded")
        time.sleep(1)
        save_shot(page, "customer_payments_full.png")

        browser.close()
        print("All high-resolution full screenshots captured successfully!")

if __name__ == "__main__":
    run_capture()
