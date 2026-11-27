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
it("keeps an authenticated empty server manifest empty", async () => {
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
    expect(snapshot.deliveries).toEqual([]);
    expect(await workflow.deliveryTasks()).toEqual([]);
});

it.each([0, 1, 2])(
    "binds %i native DOs by outlet_id, independent of outlet array order",
    async (count) => {
        const fixture = new MockProvider("delivery");
        const raw = await fixture.snapshot();
        const identity = await fixture.bootstrap();
        const outlets = raw.outlets
            .slice(0, Math.max(1, count))
            .map((outlet, i) => ({
                ...outlet,
                id: `assigned/${i}`,
                name: `Assigned ${i}`,
                address: `Address ${i}`,
                latitude: 1 + i,
                longitude: 120 + i,
            }));
        const deliveries = raw.deliveries
            .slice(0, count)
            .map((delivery, i) => ({
                ...delivery,
                id: `WH/OUT/${String(i + 1).padStart(5, "0")}`,
                outlet_id: outlets[i].id,
                outlet: outlets[i].name,
                address: outlets[i].address,
                owner: `${identity.companyId}:${identity.id}`,
                business_date: identity.businessDate,
                site: {
                    latitude: outlets[i].latitude,
                    longitude: outlets[i].longitude,
                    radius: outlets[i].radius,
                },
                lines: [
                    {
                        id: `stock-move-${i + 1}`,
                        name: `[SKU-${i + 1}] Native product ${i + 1}`,
                        quantity: i + 2,
                        unit: "Units",
                    },
                ],
            }));
        const source = {
            bootstrap: async () => identity,
            snapshot: async () => ({ ...raw, outlets, deliveries }),
        };
        const provider = new MockProvider("delivery", false, source);
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
            expect(task.id).toMatch(/^WH\/OUT\//);
            expect(task.lines[0].name).toContain("Native product");
        }
        outlets.reverse();
        expect(
            (await provider.deliveryTasks()).sort((a, b) =>
                a.id.localeCompare(b.id),
            ),
        ).toEqual(tasks.sort((a, b) => a.id.localeCompare(b.id)));
        const store = new FieldStore(crypto.randomUUID());
        try {
            const morning = new MorningSimulation(store, identity, provider);
            vi.stubGlobal("navigator", { onLine: true });
            const session = await morning.openDay();
            expect(session.deliveryManifest).toEqual(tasks);
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
        (await new MockProvider("delivery", false, source).snapshot())
            .deliveries,
    ).toEqual(raw.deliveries);
    source.snapshot = async () => ({ ...raw, deliveries: [] });
    expect(
        (await new MockProvider("sales", true, source).snapshot()).deliveries,
    ).toEqual([]);
});

it("forwards live sales.order.submit to authenticated.submit when available", async () => {
    vi.stubGlobal("navigator", { onLine: true });
    try {
        const fixture = new MockProvider("sales");
        const mockReceipt = {
            client_uuid: "client-order-1",
            status: "accepted" as const,
            message: "Pesanan SO0042 berhasil diajukan.",
            reference: "SO0042",
        };
        const submitSpy = vi.fn(async () => mockReceipt);
        const source = {
            bootstrap: () => fixture.bootstrap(),
            snapshot: () => fixture.snapshot(),
            submit: submitSpy,
        };
        const provider = new MockProvider("sales", true, source as any);
        const cmd = {
            schema_version: 1 as const,
            client_uuid: "client-order-1",
            type: "sales.order.submit" as const,
            occurred_at: new Date().toISOString(),
            payload: {
                outlet_id: "10",
                lines: [{ product_id: "1", qty: "5", uom: "carton" }],
            },
        };
        const receipt = await provider.submit(cmd);
        expect(submitSpy).toHaveBeenCalledWith(cmd);
        expect(receipt).toEqual(mockReceipt);
    } finally {
        vi.unstubAllGlobals();
    }
});

it("forwards authenticated POD and trip closing with their idempotency UUIDs", async () => {
    vi.stubGlobal("navigator", { onLine: true });
    try {
        const fixture = new MockProvider("delivery");
        const submitSpy = vi.fn(async (command: any) => ({
            client_uuid: command.client_uuid,
            status: "accepted" as const,
            message: "Accepted by Odoo",
            reference:
                command.type === "delivery.pod.submit"
                    ? "POD-OFFICIAL"
                    : "TRIP-OFFICIAL",
        }));
        const source = {
            bootstrap: () => fixture.bootstrap(),
            snapshot: () => fixture.snapshot(),
            submit: submitSpy,
        };
        const provider = new MockProvider("delivery", true, source as any);

        // Both writes preserve the UUID generated by the outbox command.
        const podCmd = {
            schema_version: 1 as const,
            client_uuid: "pod-demo-1",
            type: "delivery.pod.submit" as const,
            occurred_at: new Date().toISOString(),
            payload: {
                source: { id: "DEMO-DO-001", trip: "TRIP-01" },
                recipient: "Budi",
            },
        };
        const podReceipt = await provider.submit(podCmd as any);
        expect(submitSpy).toHaveBeenCalledWith(podCmd);
        expect(podReceipt.reference).toBe("POD-OFFICIAL");

        const closeCmd = {
            schema_version: 1 as const,
            client_uuid: "trip-close-1",
            type: "delivery.trip.close" as const,
            occurred_at: new Date().toISOString(),
            payload: {
                trip_id: "TRIP-01",
                vehicle: "DB 8471 MD",
            },
        };
        const closeReceipt = await provider.submit(closeCmd as any);
        expect(submitSpy).toHaveBeenCalledWith(closeCmd);
        expect(closeReceipt.reference).toBe("TRIP-OFFICIAL");
        expect(submitSpy).toHaveBeenCalledTimes(2);
    } finally {
        vi.unstubAllGlobals();
    }
});
