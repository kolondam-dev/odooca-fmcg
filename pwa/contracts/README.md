# Kontrak client draft v0.1

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
