import { describe, expect, it } from "vitest";
import { RouteSchema } from "../src/ui/navigation";
describe("history route input", () => {
    it("allows only route metadata, never saved coordinates or media", () => {
        expect(
            RouteSchema.safeParse({
                page: "sales",
                outlet: "CUST-1",
                dialog: { type: "order", outlet: "CUST-1" },
            }).success,
        ).toBe(true);
        for (const value of [
            { page: "admin" },
            { page: "sales", outlet: 1 },
            { page: "home", latitude: 1 },
            { page: "home", dialog: { type: "order" } },
            { page: "home", dialog: { type: "attendance", event: "unknown" } },
            {
                page: "home",
                dialog: { type: "attendance", photo: "data:image/png" },
            },
        ])
            expect(RouteSchema.safeParse(value).success).toBe(false);
    });
});
