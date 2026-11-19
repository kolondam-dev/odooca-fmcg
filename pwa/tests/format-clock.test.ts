import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { clockHM, clockHMS, time } from "../src/domain/format";

describe("clockHMS (waktu kejadian, selalu berdetik)", () => {
    it("memakai titik, 24 jam, WITA, lengkap dengan detik", () => {
        expect(clockHMS("2026-11-18T00:30:07Z")).toBe("08.30.07");
        expect(clockHMS("2026-11-18T01:05:59Z")).toBe("09.05.59");
        expect(clockHMS("2026-11-17T16:00:00Z")).toBe("00.00.00");
        expect(clockHMS("2026-11-18T15:59:59Z")).toBe("23.59.59");
    });
    it("menerima Date dan epoch", () => {
        expect(clockHMS(new Date("2026-11-18T00:30:07Z"))).toBe("08.30.07");
        expect(clockHMS(Date.parse("2026-11-18T00:30:07Z"))).toBe("08.30.07");
    });
    it("kosong atau tidak valid -> teks kosong", () => {
        for (const bad of [undefined, null, "", "bukan tanggal"])
            expect(clockHMS(bad as never)).toBe("");
    });
    it("time() juga berdetik", () => {
        expect(time("2026-11-18T00:30:07Z")).toBe("08.30.07");
    });
});

describe("clockHM (jam rencana, tanpa detik)", () => {
    it("hanya untuk slot jadwal", () => {
        expect(clockHM("2026-11-18T00:30:07Z")).toBe("08.30");
        expect(clockHM("")).toBe("");
    });
});

/** K12: waktu yang tercatat tidak boleh tampil hanya HH.mm. */
describe("penjaga jam kejadian", () => {
    const dir = join(__dirname, "../src");
    const files = (d: string): string[] =>
        readdirSync(d, { withFileTypes: true }).flatMap((e) =>
            e.isDirectory()
                ? files(join(d, e.name))
                : /\.tsx?$/.test(e.name)
                  ? [join(d, e.name)]
                  : [],
        );
    const sources = files(dir).map(
        (f) => [f, readFileSync(f, "utf8")] as const,
    );
    it("clockHM( hanya dipakai di format.ts", () => {
        const offenders = sources
            .filter(([f]) => !f.endsWith("domain/format.ts"))
            .filter(([, s]) => /\bclockHM\(/.test(s))
            .map(([f]) => f);
        expect(offenders).toEqual([]);
    });
    it("format jam Intl selalu memuat detik", () => {
        const offenders = sources
            .filter(([f]) => !f.endsWith("domain/format.ts"))
            .filter(
                ([, s]) =>
                    /\bhour:\s*"(?:2-digit|numeric)"/.test(s) &&
                    !/\bsecond:\s*"(?:2-digit|numeric)"/.test(s),
            )
            .map(([f]) => f);
        expect(offenders).toEqual([]);
    });
});
