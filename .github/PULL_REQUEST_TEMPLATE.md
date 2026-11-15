## Ringkasan

- Perubahan:
- Risiko yang ditutup:

## CI impact plan

Jalankan `python scripts/ci/plan.py --base origin/main --head HEAD`.

- Suite terpilih:
- Alasan utama:
- Path tidak dikenal: tidak ada / jelaskan
- Perlu `full-ci` atau release gate: ya/tidak — alasan

## Verifikasi

- [ ] `ruff check .`
- [ ] `python scripts/check_manifests.py`
- [ ] Test targeted hasil planner dijalankan/menunggu CI
- [ ] Test baru memiliki suite, trigger, budget, isolasi, bukti, dan pemilik
- [ ] Perubahan impact map memiliki counterexample di `tests/test_ci_impact.py`

## Belum diuji

- [BU]

> Label hanya boleh menambah cakupan. Jangan memakai perubahan workflow atau
> selector untuk menghindari suite minimum hasil planner.
