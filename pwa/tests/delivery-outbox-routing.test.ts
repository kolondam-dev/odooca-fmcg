import { afterEach, expect, it, vi } from "vitest";

vi.mock("../src/domain/delivery", async (importOriginal) => ({
    ...(await importOriginal<typeof import("../src/domain/delivery")>()),
    assertPodSource: vi.fn(() => undefined),
    validatePodCommit: vi.fn(() => undefined),
    validatePodMedia: vi.fn(async () => undefined),
}));
vi.mock("../src/domain/trip-close", async (importOriginal) => ({
    ...(await importOriginal<typeof import("../src/domain/trip-close")>()),
    validateTripClose: vi.fn(
        (item: { command: { payload: unknown } }) => item.command.payload,
    ),
    validateTripCloseMedia: vi.fn(async () => undefined),
}));
vi.mock("../src/domain/evidence-package", async (importOriginal) => ({
    ...(await importOriginal<
        typeof import("../src/domain/evidence-package")
    >()),
    validatePackagedCommandEvidence: vi.fn(async () => undefined),
}));

import { ApiError, type FieldProvider } from "../src/domain/contracts";
import { Outbox } from "../src/domain/outbox";
import { DEMO_OFFICE } from "../src/domain/trip-close-contracts";
import { FieldStore } from "../src/storage/store";

let store: FieldStore | undefined;

afterEach(async () => {
    await store?.close();
    vi.unstubAllGlobals();
});

it("routes POD and closing once with unchanged UUIDs and terminally rejects server 422", async () => {
    vi.stubGlobal("navigator", { onLine: true });
    store = new FieldStore(`delivery-routing-${crypto.randomUUID()}`);
    const owner = "company-1:driver-1";
    const podUuid = crypto.randomUUID();
    const closeUuid = crypto.randomUUID();
    const occurredAt = new Date().toISOString();
    const businessDate = new Date().toLocaleDateString("en-CA", {
        timeZone: "Asia/Makassar",
    });
    const submitted: string[] = [];
    const provider: FieldProvider = {
        mode: "live",
        bootstrap: vi.fn(),
        snapshot: vi.fn(),
        submit: vi.fn(async (command) => {
            submitted.push(command.client_uuid);
            if (command.type === "delivery.trip.close")
                throw new ApiError(
                    422,
                    "DO kedua belum memiliki POD yang diterima hari ini.",
                );
            return {
                client_uuid: command.client_uuid,
                status: "accepted" as const,
                reference: "POD-OFFICIAL",
                message: "Accepted by Odoo",
            };
        }),
    };
    const engine = new Outbox(store, owner, provider);
    const source = {
        id: "WH/OUT/06409",
        trip: "TRIP-ACC-01",
        vehicle: "DB 8123 QA",
        outlet: "FreshMart Bahu",
        outlet_id: "outlet-8",
        address: "Bahu",
        owner,
        business_date: businessDate,
        version: "odoo-delivery-v1:abc",
        site: { latitude: 1.465, longitude: 124.833, radius: 100 },
        lines: [
            {
                id: "move-1",
                name: "[SKU-1] Product",
                quantity: 2,
                unit: "Units",
            },
        ],
    };
    const evidence = {
        id: crypto.randomUUID(),
        packageHash: "a".repeat(64),
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
        capturedAt: occurredAt,
    };
    const pod = {
        pod_version: 1 as const,
        source,
        recipient: "Budi",
        outcome: "delivered" as const,
        reason: "",
        lines: [{ id: "move-1", received: 2 }],
        evidence,
    };
    const podCommand = {
        schema_version: 1 as const,
        client_uuid: podUuid,
        type: "delivery.pod.submit" as const,
        occurred_at: occurredAt,
        payload: pod,
    };
    await engine.enqueue("delivery.pod.submit", pod, "POD", podUuid, {
        key: "delivery-pod:WH/OUT/06409",
        expected: undefined,
        value: podCommand,
        occurredAt,
    });

    const closing = {
        trip_id: source.trip,
        business_date: businessDate,
        daily_source: { test: true },
        office: DEMO_OFFICE,
        fix: {
            latitude: DEMO_OFFICE.latitude,
            longitude: DEMO_OFFICE.longitude,
            accuracy: 3,
            sampled_at: occurredAt,
        },
        pod_uuids: [podUuid],
    };
    const closeCommand = {
        schema_version: 1 as const,
        client_uuid: closeUuid,
        type: "delivery.trip.close" as const,
        occurred_at: occurredAt,
        payload: closing,
    };
    // Closing creation/CAS has dedicated tests. Insert the validated command
    // here so this test isolates transport and terminal outbox semantics.
    await store.put({
        key: `${owner}:${closeUuid}`,
        owner,
        command: closeCommand,
        label: "Closing",
        state: "queued",
        attempts: 0,
        nextAttempt: 0,
    });

    await engine.flush();
    expect([...submitted].sort()).toEqual([podUuid, closeUuid].sort());
    expect(provider.submit).toHaveBeenCalledTimes(2);
    expect(
        (await store.list(owner)).map((row) => row.command.client_uuid).sort(),
    ).toEqual([podUuid, closeUuid].sort());
    expect(await store.list(owner)).toEqual(
        expect.arrayContaining([
            expect.objectContaining({ state: "accepted" }),
            expect.objectContaining({
                state: "rejected",
                error: "DO kedua belum memiliki POD yang diterima hari ini.",
            }),
        ]),
    );

    await engine.retry();
    await engine.flush();
    expect([...submitted].sort()).toEqual([podUuid, closeUuid].sort());
    await expect(
        engine.enqueue("delivery.pod.submit", pod, "duplicate", podUuid, {
            key: "duplicate",
            expected: undefined,
            value: podCommand,
            occurredAt,
        }),
    ).rejects.toThrow("Command UUID sudah digunakan");
    expect(await store.list(owner)).toHaveLength(2);
});
