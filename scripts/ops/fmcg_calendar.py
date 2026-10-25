"""Kanonikal Kalender Operasional Distributor FMCG Manado (Tahun 2026).

Menjadi single source of truth untuk:
1. PJP (Permanent Journey Plan) kunjungan salesman.
2. Penjadwalan Sales Order (SO) dan Delivery Order (DO).
3. Penentuan hari kerja operasional (working days) vs hari libur operasional.

Referensi Resmi Hari Libur Nasional & Cuti Bersama 2026:
- SKB 3 Menteri (Menteri Agama, Menteri Ketenagakerjaan, Menteri PANRB) Tahun 2026
  (Nomor 1017 Tahun 2025, Nomor 2 Tahun 2025, Nomor 2 Tahun 2025).
- Publikasi Resmi Kemenko PMK:
  https://www.kemenkopmk.go.id/pemerintah-tetapkan-17-hari-libur-nasional-dan-8-hari-cuti-bersama-tahun-2026
  (Tahun Baru Islam 1448 H jatuh pada 16 JUNI 2026, BUKAN 16 Juli 2026).
- Pada bulan Juli 2026: TIDAK ADA hari libur nasional maupun cuti bersama.
- Hari libur operasional di bulan Juli 2026 HANYA hari Minggu (5, 12, 19, 26 Juli 2026).
"""

import datetime as dt

# Hari Libur Nasional Resmi Indonesia 2026 (17 Hari - SKB 3 Menteri No. 1017/2025)
# Referensi: Kemenko PMK (16 Juni 2026: Tahun Baru Islam 1448 H; Juli 2026: nihil libur nasional)
NATIONAL_HOLIDAYS_2026 = {
    dt.date(2026, 1, 1): "Tahun Baru 2026 Masehi",
    dt.date(2026, 1, 16): "Isra Mikraj Nabi Muhammad SAW",
    dt.date(2026, 2, 17): "Tahun Baru Imlek 2577 Kongzili",
    dt.date(2026, 3, 19): "Hari Suci Nyepi (Tahun Baru Saka 1948)",
    dt.date(2026, 3, 21): "Hari Raya Idul Fitri 1447 H (Hari Pertama)",
    dt.date(2026, 3, 22): "Hari Raya Idul Fitri 1447 H (Hari Kedua)",
    dt.date(2026, 4, 3): "Wafat Yesus Kristus",
    dt.date(2026, 4, 5): "Kebangkitan Yesus Kristus (Paskah)",
    dt.date(2026, 5, 1): "Hari Buruh Internasional",
    dt.date(2026, 5, 14): "Kenaikan Yesus Kristus",
    dt.date(2026, 5, 27): "Hari Raya Idul Adha 1447 Hijriah",
    dt.date(2026, 5, 31): "Hari Suci Waisak 2570 BE",
    dt.date(2026, 6, 1): "Hari Lahir Pancasila",
    dt.date(2026, 6, 16): "Tahun Baru Islam 1448 Hijriah",
    dt.date(2026, 8, 17): "Hari Proklamasi Kemerdekaan RI Ke-81",
    dt.date(2026, 8, 25): "Maulid Nabi Muhammad SAW",
    dt.date(2026, 12, 25): "Hari Raya Natal",
}


def is_working_day(d: dt.date) -> bool:
    """Menentukan apakah tanggal d adalah hari kerja operasional distributor FMCG Manado.
    - Senin s/d Sabtu: Hari kerja operasional (armada delivery & sales beroperasi).
    - Minggu: Hari libur mingguan operasional.
    - Hari Libur Nasional (SKB 3 Menteri): Hari libur operasional.
    """
    if d.weekday() == 6:  # Minggu
        return False
    if d in NATIONAL_HOLIDAYS_2026:
        return False
    return True


def get_next_working_day(d: dt.date, offset_days: int = 1) -> dt.date:
    """Menghitung tanggal hari kerja operasional berikutnya setelah tanggal d.
    Secara default melangkah offset_days (default H+1), lalu melompati hari Minggu
    atau hari libur nasional hingga menemukan hari kerja operasional.
    """
    curr = d + dt.timedelta(days=offset_days)
    while not is_working_day(curr):
        curr += dt.timedelta(days=1)
    return curr
