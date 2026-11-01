import { expect, it, vi } from "vitest";
import { MockProvider } from "../src/data/mock";
import { ApiError } from "../src/domain/contracts";
it("uses the authenticated identity and keeps remote-demo allowance out of the server snapshot", async () => {
    const fixture = new MockProvider("sales");
    const raw = await fixture.snapshot();
    const identity = {
        ...(await fixture.bootstrap()),
        id: "server-user",
        companyId: "server-company",
        name: "Karyawan Odoo",
    };
    const source = {
        bootstrap: vi.fn(async () => identity),
        snapshot: vi.fn(async () => raw),
    };
    const workflow = new MockProvider("sales", true, source);
    expect(await workflow.bootstrap()).toEqual(identity);
    const local = await workflow.snapshot();
    expect(local.outlets.every((outlet) => outlet.demo_unrestricted)).toBe(
        true,
    );
    expect(
        raw.outlets.every((outlet) => outlet.demo_unrestricted === undefined),
    ).toBe(true);
    expect(
        local.outlets.map((outlet) => [
            outlet.id,
            outlet.latitude,
            outlet.longitude,
        ]),
    ).toEqual(
        raw.outlets.map((outlet) => [
            outlet.id,
            outlet.latitude,
            outlet.longitude,
        ]),
    );
    expect(local.version).toBe(raw.version);
});
it("never falls back to a persona or catalog when authenticated reads fail", async () => {
    const denied = async (): Promise<never> => {
        throw new ApiError(401, "Session ended");
    };
    const workflow = new MockProvider("sales", true, {
        bootstrap: denied,
        snapshot: denied,
    });
    await expect(workflow.bootstrap()).rejects.toThrow("Session ended");
    await expect(workflow.snapshot()).rejects.toThrow("Session ended");
});
