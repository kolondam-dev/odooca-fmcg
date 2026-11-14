import { describe, expect, it } from "vitest";
import { LeaveRequestSchema, workingDays } from "../src/domain/leave.ts";

describe("leave", () => {
    it("hanya menghitung Senin–Jumat dan menolak rentang terbalik", () => {
        expect(workingDays("2026-11-12", "2026-11-13")).toBe(2);
        expect(workingDays("2026-11-13", "2026-11-16")).toBe(2);
        expect(workingDays("2026-11-14", "2026-11-15")).toBe(0);
        expect(workingDays("2026-11-13", "2026-11-12")).toBeUndefined();
        expect(workingDays("", "2026-11-12")).toBeUndefined();
    });
    it("payload mengikuti kontrak server yang ada", () => {
        const ok = {
            date_from: "2026-11-12",
            date_to: "2026-11-13",
            reason: "Acara keluarga",
        };
        expect(LeaveRequestSchema.safeParse(ok).success).toBe(true);
        expect(
            LeaveRequestSchema.safeParse({ ...ok, date_to: "2026-11-11" })
                .success,
        ).toBe(false);
        expect(
            LeaveRequestSchema.safeParse({ ...ok, reason: "x" }).success,
        ).toBe(false);
        expect(
            LeaveRequestSchema.safeParse({ ...ok, leave_type: "sick" }).success,
        ).toBe(false);
    });
});
