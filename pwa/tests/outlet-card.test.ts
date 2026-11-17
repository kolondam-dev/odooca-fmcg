import { describe, expect, it } from "vitest";
import {
    creditExceeded,
    outletMeta,
    plannedTime,
} from "../src/domain/outlet-card";

describe("plannedTime", () => {
    it("memakai titik gaya DS dan menambah nol di depan", () => {
        expect(plannedTime("09.15")).toBe("09.15");
        expect(plannedTime("09:15")).toBe("09.15");
        expect(plannedTime("9.05")).toBe("09.05");
    });
    it("menolak format atau jam yang tidak valid", () => {
        for (const bad of ["", " ", "Pagi", "24.00", "09.60", "9", "-", "—"])
            expect(plannedTime(bad)).toBeUndefined();
        expect(plannedTime(undefined)).toBeUndefined();
        expect(plannedTime(915)).toBeUndefined();
    });
});

describe("outletMeta", () => {
    it("mengembalikan jam dan jarak yang ada", () => {
        expect(outletMeta({ time: "08.30", distance: "1,2 km" })).toEqual({
            time: "08.30",
            distance: "1,2 km",
        });
    });
    it("membuang nilai kosong dan tanda pengganti dari server", () => {
        for (const empty of ["", "  ", "-", "—", "N/A", "null"])
            expect(outletMeta({ time: empty, distance: empty })).toEqual({
                time: undefined,
                distance: undefined,
            });
    });
    it("memangkas spasi pada jarak", () => {
        expect(outletMeta({ distance: "  0,1 km " }).distance).toBe("0,1 km");
    });
});

describe("creditExceeded", () => {
    it("ada bila piutang melebihi limit, lengkap dengan TOP", () => {
        expect(
            creditExceeded({
                credit_limit: 25_000_000,
                ar_outstanding: 41_484_793,
                payment_terms: "TOP 7 hari",
            }),
        ).toEqual({
            limit: 25_000_000,
            outstanding: 41_484_793,
            terms: "TOP 7 hari",
        });
    });
    it("tidak ada bila sama dengan limit atau di bawahnya", () => {
        expect(
            creditExceeded({ credit_limit: 100, ar_outstanding: 100 }),
        ).toBeUndefined();
        expect(
            creditExceeded({ credit_limit: 100, ar_outstanding: 99 }),
        ).toBeUndefined();
    });
    it("tidak menebak bila limit atau piutang tidak diketahui", () => {
        expect(creditExceeded(undefined)).toBeUndefined();
        expect(creditExceeded(null)).toBeUndefined();
        expect(creditExceeded({ credit_limit: null, ar_outstanding: 5 })).toBe(
            undefined,
        );
        expect(
            creditExceeded({ credit_limit: 5, ar_outstanding: null }),
        ).toBeUndefined();
        expect(creditExceeded({ ar_outstanding: 5 })).toBeUndefined();
    });
    it("TOP kosong atau tanda pengganti tidak ikut ditampilkan", () => {
        expect(
            creditExceeded({
                credit_limit: 1,
                ar_outstanding: 2,
                payment_terms: " — ",
            })?.terms,
        ).toBeUndefined();
    });
});
