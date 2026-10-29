import { expect, it } from "vitest";
import { validateExpense } from "../src/domain/expense";
const request = {
    category: "fuel_planned",
    amount: "100000",
    expense_scope: "trip",
    trip_id: "TRIP-01",
    delivery_id: null,
    scheduled_date: "2026-11-01",
    odometer: 0,
    reason: "Luar kota",
    evidence: null,
};
it("validates H-1 across month/year boundary, including zero starting KM", () => {
    expect(validateExpense(request, "2026-10-31").odometer).toBe(0);
    expect(
        validateExpense(
            { ...request, scheduled_date: "2027-01-01" },
            "2026-12-31",
        ).scheduled_date,
    ).toBe("2027-01-01");
});
it("rejects same-day planned fuel and invalid calendar/business date", () => {
    expect(() => validateExpense(request, "2026-11-01")).toThrow("H-1");
    expect(() => validateExpense(request, "")).toThrow("Tanggal bisnis");
    expect(() =>
        validateExpense(
            { ...request, scheduled_date: "2026-02-30" },
            "2026-02-28",
        ),
    ).toThrow();
});
it("requires trip/DO references and a single charging scope", () => {
    expect(() =>
        validateExpense(
            { ...request, expense_scope: "delivery" },
            "2026-10-31",
        ),
    ).toThrow("referensi DO");
    expect(() =>
        validateExpense({ ...request, delivery_id: "DO-1" }, "2026-10-31"),
    ).toThrow("sekaligus");
    expect(() =>
        validateExpense({ ...request, trip_id: " " }, "2026-10-31"),
    ).toThrow();
    expect(
        validateExpense(
            { ...request, expense_scope: "delivery", delivery_id: "DO-1" },
            "2026-10-31",
        ).delivery_id,
    ).toBe("DO-1");
});
it("rejects invalid money/KM and injected approval", () => {
    for (const amount of ["0", "-1", "1.5", "NaN", "100000001", "1e5"])
        expect(() =>
            validateExpense({ ...request, amount }, "2026-10-31"),
        ).toThrow();
    for (const odometer of [null, -1, 1.5, NaN])
        expect(() =>
            validateExpense({ ...request, odometer }, "2026-10-31"),
        ).toThrow();
    expect(() =>
        validateExpense({ ...request, approved: true }, "2026-10-31"),
    ).toThrow();
});
it("allows non-fuel without KM and same-day emergency fuel without granting approval", () => {
    expect(
        validateExpense(
            { ...request, category: "meal", odometer: null },
            "2026-11-01",
        ).odometer,
    ).toBeNull();
    expect(
        validateExpense(
            { ...request, category: "fuel_emergency" },
            "2026-11-01",
        ).category,
    ).toBe("fuel_emergency");
});
