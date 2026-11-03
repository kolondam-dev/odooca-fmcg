import { FieldStore } from "../src/storage/store";
import { MorningSimulation } from "../src/domain/morning";
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
it("supplies demo delivery manifest when authenticated driver has empty server deliveries", async () => {
    const fixture = new MockProvider("delivery");
    const raw = await fixture.snapshot();
    const rawWithoutDeliveries = { ...raw, deliveries: [] };
    const identity = {
        ...(await fixture.bootstrap()),
        id: "server-driver",
        companyId: "server-company",
        name: "Eko Driver",
        roles: ["delivery" as const],
    };
    const source = {
        bootstrap: vi.fn(async () => identity),
        snapshot: vi.fn(async () => rawWithoutDeliveries),
    };
    const workflow = new MockProvider("delivery", true, source);
    const snapshot = await workflow.snapshot();
    expect(snapshot.deliveries.length).toBeGreaterThan(0);
    expect(snapshot.deliveries[0].id).toBe(
        `DEMO-DO-OUTLET-${raw.outlets[0].id}`,
    );
    const tasks = await workflow.deliveryTasks();
    expect(tasks.length).toBe(raw.outlets.length);
    expect(tasks[0].id).toBe(`DEMO-DO-OUTLET-${raw.outlets[0].id}`);
});

it.each([0, 1, 2])(
    "binds fallback DOs to all %i assigned outlets and opens the driver workday",
    async (count) => {
        const fixture = new MockProvider("delivery");
        const raw = await fixture.snapshot();
        const identity = await fixture.bootstrap();
        const outlets = raw.outlets.slice(0, count).map((outlet, i) => ({
            ...outlet,
            id: `assigned/${i}`,
            name: `Assigned ${i}`,
            address: `Address ${i}`,
            latitude: 1 + i,
            longitude: 120 + i,
        }));
        const source = {
            bootstrap: async () => identity,
            snapshot: async () => ({ ...raw, outlets, deliveries: [] }),
        };
        const provider = new MockProvider("delivery", true, source);
        const tasks = await provider.deliveryTasks();
        expect(tasks).toHaveLength(count);
        for (const task of tasks) {
            const outlet = outlets.find(
                (candidate) => candidate.id === task.outlet_id,
            )!;
            expect(task.outlet).toBe(outlet.name);
            expect(task.address).toBe(outlet.address);
            expect(task.site).toMatchObject({
                latitude: outlet.latitude,
                longitude: outlet.longitude,
                radius: outlet.radius,
            });
        }
        outlets.reverse();
        expect(
            (await provider.deliveryTasks()).sort((a, b) =>
                a.id.localeCompare(b.id),
            ),
        ).toEqual(tasks.sort((a, b) => a.id.localeCompare(b.id)));
        if (count === 0) return; // No assignment must not invent deliveries.
        const store = new FieldStore(crypto.randomUUID());
        try {
            const morning = new MorningSimulation(store, identity, provider);
            vi.stubGlobal("navigator", { onLine: true });
            const session = await morning.openDay();
            expect(session.deliveryManifest).toHaveLength(count);
        } finally {
            await store.close();
            vi.unstubAllGlobals();
        }
    },
);

it("preserves a nonempty server manifest and does not supply sales fallback DOs", async () => {
    const fixture = new MockProvider("delivery");
    const raw = await fixture.snapshot();
    const source = {
        bootstrap: () => fixture.bootstrap(),
        snapshot: async () => raw,
    };
    expect(
        (await new MockProvider("delivery", true, source).snapshot())
            .deliveries,
    ).toEqual(raw.deliveries);
    source.snapshot = async () => ({ ...raw, deliveries: [] });
    expect(
        (await new MockProvider("sales", true, source).snapshot()).deliveries,
    ).toEqual([]);
});
