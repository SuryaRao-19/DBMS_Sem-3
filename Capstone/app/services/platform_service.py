"""
Platform Identity, Verified Operator Reference, Social Links & Data Provenance Service
EZ Charge Network Portal — Independent Academic Demonstration
"""
from app.db import query_all, query_one, execute

VALID_DATA_STATUSES = (
    "VERIFIED",
    "PENDING_VERIFICATION",
    "HISTORICAL",
    "DEMO",
    "ESTIMATED",
    "UNAVAILABLE",
    "OUTDATED",
)

# Verified Tata Power EV Charging Scale (12 October 2026 Press Release Baseline)
# Source conflict note: Earlier tatapower.com/ezcharge web snapshots list 5,500+ public points
# and 620+ cities under an earlier publication date/scope; both are disclosed without fabrication.
OFFICIAL_EZCHARGE_STATS = [
    {
        "value": "6,700+",
        "label": "Public, Semi-Public & Fleet Charging Points",
        "source_label": "Tata Power EV Charging Press Release",
        "source_url": "https://www.tatapower.com/news-and-media/media-releases",
        "published_date": "2026-10-12",
        "verified_date": "2026-11-12",
        "scope_note": "Includes public, semi-public & fleet AC/DC points nationwide.",
    },
    {
        "value": "2.5 Lakh+",
        "label": "Home Chargers Installed Across India",
        "source_label": "Tata Power EV Charging Press Release",
        "source_url": "https://www.tatapower.com/news-and-media/media-releases",
        "published_date": "2026-10-12",
        "verified_date": "2026-11-12",
        "scope_note": "Residential wallbox & home installation cumulative baseline.",
    },
    {
        "value": "1,200+",
        "label": "E-Bus Fleet Charging Points",
        "source_label": "Tata Power EV Charging Press Release",
        "source_url": "https://www.tatapower.com/news-and-media/media-releases",
        "published_date": "2026-10-12",
        "verified_date": "2026-11-12",
        "scope_note": "Heavy-duty municipal and electric bus depot points.",
    },
    {
        "value": "7 Lakh+",
        "label": "Registered Customers",
        "source_label": "Tata Power EV Charging Press Release",
        "source_url": "https://www.tatapower.com/news-and-media/media-releases",
        "published_date": "2026-10-12",
        "verified_date": "2026-11-12",
        "scope_note": "Reported registered user base on Tata Power EZ Charge platform.",
    },
    {
        "value": "700+",
        "label": "Cities & Towns Covered Pan-India",
        "source_label": "Tata Power EV Charging Press Release",
        "source_url": "https://www.tatapower.com/ezcharge",
        "published_date": "2026-10-12",
        "verified_date": "2026-11-12",
        "scope_note": "Historical web portal snapshots cite 5,500+ points / 620+ cities from earlier dates.",
    },
]

# Official Tata Power corporate announcements (no invented news items)
VERIFIED_ANNOUNCEMENTS = [
    {
        "title": "6,700+ Charging Points & 2.5 Lakh+ Home Chargers Nationwide Milestone",
        "date": "2026-10-12",
        "summary": "Tata Power reported scaling its EZ Charge ecosystem past 6,700+ public/semi-public/fleet charging points, 2.5 lakh+ home chargers, 1,200+ e-bus points, and 7 lakh+ registered customers across 700+ cities & towns.",
        "source_name": "Tata Power Official Press Release",
        "source_url": "https://www.tatapower.com/news-and-media/media-releases",
        "status": "VERIFIED",
    },
    {
        "title": "Yamuna Expressway High-Capacity DC Mega Charging Corridors",
        "date": "2026-09-01",
        "summary": "Tata Power announced high-speed 120 kW & 60 kW multi-gun charging stations at Yamuna Expressway LHS 35 KM, LHS 107 KM, RHS 100 KM, and RHS 16 KM milestones (coordinates flagged PENDING_VERIFICATION in this portal until GPS verified).",
        "source_name": "Tata Power Highway Corridor Release",
        "source_url": "https://www.tatapower.com/news-and-media/media-releases",
        "status": "VERIFIED",
    },
    {
        "title": "Dr. Ambedkar International Centre Public EV Charging Installation",
        "date": "2023-04-01",
        "summary": "Public EV charging facility inaugurated at 15, Janpath, New Delhi in collaboration with the Dr. Ambedkar Foundation to expand central Delhi e-mobility access.",
        "source_name": "Tata Power EZ Charge Portal",
        "source_url": "https://www.tatapower.com/ezcharge",
        "status": "VERIFIED",
    },
    {
        "title": "Academic Portal Simulation & Hardware Separation Policy",
        "date": "2026-11-12",
        "summary": "EZ Charge Network Portal is an independent academic demonstration: real Tata Power locations & press figures are source-attributed, while bookings, QR scans, metering, and Razorpay Test Mode billing run in local MySQL sandbox mode.",
        "source_name": "EZ Charge Network Portal Integrity Policy",
        "source_url": None,
        "status": "DEMO",
    },
]


DEFAULT_OPERATOR = {
    "operator_name": "Tata Power EZ Charge",
    "parent_company": "The Tata Power Company Limited",
    "official_website": "https://www.tatapower.com/ezcharge/",
    "play_store_url": "https://play.google.com/store/apps/details?id=com.tatapower.evapp",
    "app_store_url": "https://apps.apple.com/in/app/tata-power-ez-charge/id1496350476",
    "linktree_url": "https://linktr.ee/Tata_Power_EZ_Charge",
    "support_phone": "1800 833 2233",
    "support_email": "evsupport@tatapower.com",
    "network_scale_summary": "6,700+ public/fleet points, 2.5 lakh+ home chargers across 700+ cities",
    "cities_coverage_summary": "700+ cities and nationwide highways",
    "mission_text": "Empower a billion lives through sustainable, clean energy mobility.",
    "vision_text": "India's most accessible, reliable, and verified EV charging ecosystem.",
    "is_independent_case_study": 1,
    "verification_status": "VERIFIED",
    "source_url": "https://www.tatapower.com/ezcharge/",
}

DEFAULT_SOCIAL_LINKS = [
    {"platform": "INSTAGRAM", "display_label": "Instagram", "handle": "@tatapowercompanyltd", "url": "https://www.instagram.com/tatapowercompanyltd/"},
    {"platform": "FACEBOOK", "display_label": "Facebook", "handle": "@tatapower", "url": "https://www.facebook.com/tatapower/"},
    {"platform": "LINKEDIN", "display_label": "LinkedIn", "handle": "Tata Power", "url": "https://www.linkedin.com/company/tata-power/"},
    {"platform": "X_TWITTER", "display_label": "X (Twitter)", "handle": "@tatapower", "url": "https://x.com/tatapower"},
    {"platform": "WEBSITE", "display_label": "Official EZ Charge Portal", "handle": "EZ Charge", "url": "https://www.tatapower.com/ezcharge/"},
]


def get_platform_operator():
    """Retrieve verified reference operator profile from MySQL."""
    try:
        row = query_one(
            "SELECT operator_id, operator_name, parent_company, official_website, "
            "       play_store_url, app_store_url, linktree_url, support_phone, support_email, "
            "       network_scale_summary, cities_coverage_summary, mission_text, vision_text, "
            "       services_summary, is_independent_case_study, verification_status, "
            "       source_url, last_verified_at "
            "FROM NetworkOperators ORDER BY operator_id LIMIT 1"
        )
        return row or DEFAULT_OPERATOR
    except Exception:
        return DEFAULT_OPERATOR


def get_verified_social_links():
    """Retrieve verified corporate social media links."""
    try:
        rows = query_all(
            "SELECT social_id, platform, display_label, handle, url, verification_status, source_url, last_verified_at "
            "FROM SocialLinks ORDER BY FIELD(platform, 'INSTAGRAM', 'FACEBOOK', 'LINKEDIN', 'X_TWITTER', 'YOUTUBE', 'WEBSITE')"
        )
        return rows if rows else DEFAULT_SOCIAL_LINKS
    except Exception:
        return DEFAULT_SOCIAL_LINKS


def get_data_sources():
    """Retrieve the complete Data Source Register with full provenance fields."""
    try:
        return query_all(
            "SELECT source_id, data_item, category, source_name, source_type, source_url, "
            "       published_at, retrieved_at, verification_date, data_status, "
            "       confidence_level, record_origin, associated_record_count, notes, last_updated "
            "FROM DataSources "
            "ORDER BY FIELD(data_status, 'VERIFIED', 'PENDING_VERIFICATION', 'ESTIMATED', 'DEMO', 'HISTORICAL', 'UNAVAILABLE', 'OUTDATED'), source_id"
        )
    except Exception:
        return []


def update_data_source(source_id, data_status, notes=None):
    """Admin action: update verification status and notes on a DataSources record."""
    normalized = (data_status or "").strip().upper()
    if normalized not in VALID_DATA_STATUSES:
        return False, f"Invalid status '{data_status}'. Must be one of {', '.join(VALID_DATA_STATUSES)}."

    row = query_one("SELECT source_id FROM DataSources WHERE source_id = %s", (source_id,))
    if not row:
        return False, "Data source entry not found."

    execute(
        "UPDATE DataSources SET data_status = %s, notes = COALESCE(%s, notes), verification_date = CURDATE() WHERE source_id = %s",
        (normalized, notes.strip() if notes else None, source_id),
    )
    return True, f"Data source #{source_id} updated to {normalized}."
