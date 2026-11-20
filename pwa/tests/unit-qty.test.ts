import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { splitUnits, stockUnits, unitLabel } from "../src/domain/unit-qty";

const per = { carton: 144, pack: 12 };

describe("splitUnits", () => {
    it("memecah karton → pack → pcs", () => {
        expect(splitUnits(144 + 24 + 3, per)).toEqual({
            carton: 1,
            pack: 2,
            pcs: 3,
        });
    });
    it("nol dan negatif menjadi nol", () => {
        expect(splitUnits(0, per)).toEqual({ carton: 0, pack: 0, pcs: 0 });
        expect(splitUnits(-5, per)).toEqual({ carton: 0, pack: 0, pcs: 0 });
    });
    it("tanpa tingkat pack (pack = karton) tidak mengisi pack", () => {
        expect(splitUnits(150, { carton: 144, pack: 144 })).toEqual({
            carton: 1,
            pack: 0,
            pcs: 6,
        });
    });
    it("hanya pcs bila kurang dari satu pack", () => {
        expect(splitUnits(11, per)).toEqual({ carton: 0, pack: 0, pcs: 11 });
    });
    it("stok pecahan karton dibulatkan ke pcs", () => {
        const p = { packaging: { carton: 144, pack: 12, pcs: 1 as const } };
        expect(stockUnits(p, 41.5)).toEqual({ carton: 41, pack: 6, pcs: 0 });
    });
});

describe("unitLabel", () => {
    it("hanya tingkat > 0", () => {
        expect(unitLabel({ carton: 1, pcs: 3 })).toBe("1 karton, 3 pcs");
        expect(unitLabel({})).toBe("0");
    });
});

describe("penjaga migrasi UnitQty", () => {
    it("komponen tidak lagi menulis singkatan krt/pak", () => {
        const dir = new URL("../src/components/", import.meta.url);
        for (const f of readdirSync(dir)) {
            if (!f.endsWith(".tsx")) continue;
            const src = readFileSync(new URL(f, dir), "utf8");
            expect(src, f).not.toMatch(/["'`]\s*krt\b|\bkrt["'`]|\bpak["'`]/);
        }
    });
});
