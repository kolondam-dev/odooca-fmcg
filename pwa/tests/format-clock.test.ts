import { describe, expect, it } from "vitest";
import { clockHM, time } from "../src/domain/format";

describe("clockHM", () => {
    it("memakai titik, 24 jam, dan WITA", () => {
        expect(clockHM("2026-11-18T00:30:00Z")).toBe("08.30");
        expect(clockHM("2026-11-18T01:05:00Z")).toBe("09.05");
        expect(clockHM("2026-11-17T16:00:00Z")).toBe("00.00");
        expect(clockHM("2026-11-18T15:59:00Z")).toBe("23.59");
    });
    it("menerima Date dan epoch", () => {
        expect(clockHM(new Date("2026-11-18T00:30:00Z"))).toBe("08.30");
        expect(clockHM(Date.parse("2026-11-18T00:30:00Z"))).toBe("08.30");
    });
    it("kosong atau tidak valid -> teks kosong", () => {
        for (const bad of [undefined, null, "", "bukan tanggal"])
            expect(clockHM(bad as never)).toBe("");
    });
    it("time() memakai format yang sama", () => {
        expect(time("2026-11-18T00:30:00Z")).toBe("08.30");
    });
});
