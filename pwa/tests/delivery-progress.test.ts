import { describe, expect, it } from "vitest";
import {
    deliveryProgress,
    loadSummary,
    navigationUrl,
} from "../src/domain/delivery-progress";
import type { Snapshot } from "../src/domain/contracts";
import type { DeliveryTask } from "../src/domain/delivery-contracts";
import type { QueueItem } from "../src/storage/store";

const task = (
    id: string,
    trip: string,
    outlet: string,
    lines: [number, string][],
) =>
    ({
        id,
        trip,
        vehicle: "B 1 X",
        outlet: `Toko ${outlet}`,
        outlet_id: outlet,
        address: "Jl. A",
        owner: "c:u",
        business_date: "2026-11-15",
        version: "1",
        site: { latitude: 1.4, longitude: 124.8, radius: 50 },
        lines: lines.map(([quantity, unit], i) => ({
            id: `l${i}`,
            name: "SKU",
            quantity,
            unit,
        })),
    }) as DeliveryTask;
const pod = (source: DeliveryTask) =>
    ({
        state: "queued",
        command: { type: "delivery.pod.submit", payload: { source } },
    }) as unknown as QueueItem;

describe("delivery-progress", () => {
    const a = task("DO-1", "T1", "A", [
        [20, "karton"],
        [8, "pak"],
    ]);
    const b = task("DO-2", "T1", "B", [[5, "karton"]]);
    const c = task("DO-3", "T2", "A", [[1, "pak"]]);

    it("merangkum muatan per satuan", () => {
        expect(loadSummary([a])).toBe("20 karton · 8 pak");
        expect(loadSummary([a, b])).toBe("25 karton · 8 pak");
    });
    it("menghitung total, toko unik dan DO selesai dari POD antrean", () => {
        const p = deliveryProgress([a, b, c], [pod(a)]);
        expect(p).toMatchObject({ total: 3, stores: 2, done: 1 });
        expect(p.nextTask?.id).toBe("DO-2");
        expect(p.nextTrip).toMatchObject({ name: "T1", finished: 1 });
    });
    it("memulihkan POD hanya untuk sumber manifest yang sama", () => {
        const snapshot = {
            deliveries: [a, b],
            accepted_delivery_pods: {
                [a.id]: "11111111-1111-4111-8111-111111111111",
            },
        } as Snapshot;
        expect(deliveryProgress([a, b], [], snapshot).done).toBe(1);
        expect(deliveryProgress([a, b], [], snapshot).nextTask).toBe(b);
        expect(
            deliveryProgress([{ ...a, version: "changed" }, b], [], snapshot)
                .done,
        ).toBe(0);
    });
    it("POD ditolak server (bisnis) tidak dihitung selesai", () => {
        const uuid = "11111111-1111-4111-8111-111111111111";
        const rejected = {
            state: "rejected",
            command: {
                client_uuid: uuid,
                type: "delivery.pod.submit",
                payload: { source: a },
            },
            receipt: {
                client_uuid: uuid,
                status: "rejected",
                reference: "x",
                message: "ditolak",
            },
        } as unknown as QueueItem;
        expect(deliveryProgress([a, b], [rejected]).done).toBe(0);
        expect(deliveryProgress([a, b], [pod(a)]).done).toBe(1);
    });
    it("tanpa DO tersisa tidak ada tugas berikutnya", () => {
        const p = deliveryProgress([a], [pod(a)]);
        expect(p.done).toBe(1);
        expect(p.nextTask).toBeUndefined();
        expect(p.nextTrip).toBeUndefined();
    });
    it("tautan navigasi memakai koordinat tujuan", () => {
        expect(navigationUrl(1.5, 124.9)).toContain("destination=1.5,124.9");
    });
});
