# Kontrak client draft v0.13

Sumber schema: `src/domain/contracts.ts`. Jalankan `npm run contracts:export`
setelah perubahan yang direview. CI `contracts:check` membandingkan schema generated
agar contoh, DTO dan OpenAPI tidak berubah secara terpisah.

Status: **draft client-only**, belum disahkan atau diimplementasikan backend.
Command payload masih generic JSON record untuk prototyping; validasi detail per
operation, policy, media references, business revision/cursor dan batch/dependency
harus ditutup sebelum integrasi live. Validasi UI bukan authorization.

HTTP adapter tidak pernah memilih mock ketika request gagal. Build live saat ini
mengunci operasi, termasuk jika endpoint server kebetulan mengembalikan JSON yang
cocok. Mengaktifkannya memerlukan perubahan source dan penerimaan kontrak/auth/ACL,
bukan mengganti environment variable di browser.


Katalog v2 dan mapping tahap1: [catalog-v2.md](catalog-v2.md). Snapshot legacy
hanya untuk kompatibilitas source tersimpan; HTTP read berikutnya memerlukan v2.
Constraint rasio pembagian kemasan dan uniqueness field harus divalidasi backend,
selain constraint scalar JSON Schema yang diekspor.
