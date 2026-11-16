import { describe, expect, it } from "vitest";
import {
    accuracyExceeded,
    GPS_ACCURACY_LIMIT_M,
} from "../src/domain/location-accuracy";

describe("accuracyExceeded", () => {
    it("batas absen dan check-in adalah 30 m", () => {
        expect(GPS_ACCURACY_LIMIT_M).toBe(30);
    });
    it("live: tepat 30 m masih lolos, di atasnya terkunci", () => {
        expect(accuracyExceeded(30, { demo: false })).toBe(false);
        expect(accuracyExceeded(30.1, { demo: false })).toBe(true);
        expect(accuracyExceeded(85, { demo: false })).toBe(true);
    });
    it("demo dan outlet demo_unrestricted tidak dibatasi", () => {
        expect(accuracyExceeded(85, { demo: true })).toBe(false);
        expect(accuracyExceeded(85, { demo: false, unrestricted: true })).toBe(
            false,
        );
    });
    it("nilai tidak valid tidak dianggap melebihi batas", () => {
        expect(accuracyExceeded(Number.NaN, { demo: false })).toBe(false);
        expect(accuracyExceeded(Infinity, { demo: false })).toBe(false);
    });
});
