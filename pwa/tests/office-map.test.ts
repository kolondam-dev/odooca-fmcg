import { expect, it } from "vitest";
import { OfficeMapSchema } from "../src/domain/contracts";
const office = {
    id: "4",
    name: "Office",
    latitude: 1.465,
    longitude: 124.833,
    radius: 50,
    coordinate_status: "test",
};
it("requires explicit office provenance and rejects invalid or extra authority", () => {
    expect(OfficeMapSchema.parse(office).coordinate_status).toBe("test");
    for (const change of [
        { latitude: 91 },
        { radius: 0 },
        { coordinate_status: "trusted-client" },
        { allow_checkin: true },
    ])
        expect(
            OfficeMapSchema.safeParse({ ...office, ...change }).success,
        ).toBe(false);
    const { coordinate_status: _status, ...incomplete } = office;
    expect(OfficeMapSchema.safeParse(incomplete).success).toBe(false);
});
