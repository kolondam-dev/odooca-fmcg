from datetime import datetime
from zoneinfo import ZoneInfo

# Hari bisnis proyek = kalender WITA (Asia/Makassar), bukan tanggal UTC server.
BUSINESS_TZ = ZoneInfo("Asia/Makassar")


def business_date():
    """Tanggal hari bisnis saat ini (WITA); satu-satunya acuan 'hari ini' untuk aturan kredit/jatuh tempo."""
    return datetime.now(BUSINESS_TZ).date()
