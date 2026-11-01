import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
const enabled = process.argv[2] === "enabled";
const root = "dist/demo";
const info = JSON.parse(readFileSync(`${root}/build-info.json`, "utf8"));
assert.equal(
    info.qaTools,
    enabled,
    "QA tools must require the explicit demo build flag",
);
const code = readdirSync(`${root}/assets`)
    .filter((file) => file.endsWith(".js"))
    .map((file) => readFileSync(`${root}/assets/${file}`, "utf8"))
    .join("\n");
for (const label of [
    "Mode respons transaksi lokal",
    "Simulator approval diskon",
    "Proses approval & pencairan",
    "Gunakan lokasi acuan",
])
    assert.equal(
        code.includes(label),
        enabled,
        `${label}: unexpected QA control exposure`,
    );
console.log(
    `QA build boundary: ${enabled ? "enabled for regression" : "disabled for operators"}`,
);
