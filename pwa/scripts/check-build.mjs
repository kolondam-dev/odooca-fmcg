import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
for (const mode of ["demo", "live"]) {
    const dir = `dist/${mode}`;
    const files = readdirSync(dir, { recursive: true }).filter(
        (x) => typeof x === "string",
    );
    const js = files.filter((f) => f.endsWith(".js"));
    const bytes = js.reduce(
        (n, f) => n + gzipSync(readFileSync(`${dir}/${f}`)).byteLength,
        0,
    );
    const fonts = files
        .filter((f) => f.endsWith(".woff2"))
        .reduce((n, f) => n + readFileSync(`${dir}/${f}`).byteLength, 0);
    assert(bytes <= 200 * 1024, `${mode}: JS budget exceeded`);
    assert(fonts <= 100 * 1024, `${mode}: font budget exceeded`);
    const info = JSON.parse(readFileSync(`${dir}/build-info.json`, "utf8"));
    assert.equal(info.mode, mode);
    assert(
        info.assets.every(
            (p) => p.startsWith("/field/") && !p.startsWith("/api/"),
        ),
    );
    const manifest = JSON.parse(
        readFileSync(`${dir}/manifest.webmanifest`, "utf8"),
    );
    assert.equal(manifest.name, "Odoo FMCG Mobile");
    for (const asset of [
        "brand-logo.svg",
        "icon.svg",
        "icon-192.png",
        "icon-512.png",
        "favicon-32.png",
        "apple-touch-icon.png",
    ])
        assert(files.includes(asset), `Missing brand asset ${asset}`);
    assert.equal(manifest.scope, "/field/");
    assert.equal(manifest.start_url, "/field/");
    const code = js.map((f) => readFileSync(`${dir}/${f}`, "utf8")).join("\n");
    if (mode === "live") {
        for (const fixture of [
            "DEMO-ANDRE",
            "Toko Sinar Pagi",
            "demo-mdu",
            "demo-snapshot-1",
            "Simulasikan absensi diterima",
            "SIM-ATT-",
            "Simulasikan approval & pencairan",
            "SIM-EXPENSE-POLICY-1",
            "SIM-ADV-",
            "Koreksi realisasi ditolak",
            "Mulai kunjungan demo",
            "PINPOINT SIMULASI - TANPA BASEMAP",
            "Diagnosis lokal · Data simulasi.",
        ])
            assert(
                !code.includes(fixture),
                `Live build leaked fixture ${fixture}`,
            );
        assert(
            !files.some((f) => /mock-.*\.js/.test(f)),
            "Live build ships a mock adapter",
        );
        assert(
            code.includes("Integrasi layanan perusahaan belum diaktifkan."),
            "Live build must remain fail-closed",
        );
    }
    console.log(
        `${mode}: JS gzip ${(bytes / 1024).toFixed(1)} KiB; font ${(fonts / 1024).toFixed(1)} KiB; mode/scope/fixtures PASS`,
    );
}
