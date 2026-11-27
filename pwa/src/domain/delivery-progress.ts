import type { Snapshot } from "./contracts";
import type { DeliveryTask } from "./delivery-contracts";
import { businessRejected } from "./outbox-state";
import type { QueueItem } from "../storage/store";

/**
 * DO selesai hanya bila ada POD di antrean yang bersumber manifest sama dan
 * tidak ditolak server. Aturan ini juga dipakai DeliveryWorkspace.
 */
export function acceptedDeliveryPod(
    snapshot: Snapshot | null | undefined,
    task: DeliveryTask,
) {
    const receipt = snapshot?.accepted_delivery_pods?.[task.id];
    if (
        receipt &&
        snapshot?.deliveries.some(
            (source) => JSON.stringify(source) === JSON.stringify(task),
        )
    )
        return receipt;
}
export function deliveryDoneChecker(
    queue: QueueItem[],
    snapshot?: Snapshot | null,
) {
    const sources = new Set(
        queue.flatMap((r) =>
            r.command.type === "delivery.pod.submit" && !businessRejected(r)
                ? [JSON.stringify(r.command.payload.source)]
                : [],
        ),
    );
    return (t: DeliveryTask) =>
        !!acceptedDeliveryPod(snapshot, t) || sources.has(JSON.stringify(t));
}

/** Ringkasan satuan muatan, mis. "20 karton · 8 pak". */
export function loadSummary(tasks: DeliveryTask[]): string {
    const byUnit = new Map<string, number>();
    for (const t of tasks)
        for (const l of t.lines)
            byUnit.set(l.unit, (byUnit.get(l.unit) ?? 0) + l.quantity);
    return [...byUnit].map(([unit, qty]) => `${qty} ${unit}`).join(" · ");
}

export type DeliveryProgress = {
    total: number;
    stores: number;
    done: number;
    /** Trip berikutnya: trip pertama yang masih punya DO belum selesai. */
    nextTrip?: { name: string; tasks: DeliveryTask[]; finished: number };
    nextTask?: DeliveryTask;
};

export function deliveryProgress(
    tasks: DeliveryTask[],
    queue: QueueItem[],
    snapshot?: Snapshot | null,
): DeliveryProgress {
    const isDone = deliveryDoneChecker(queue, snapshot);
    const nextTask = tasks.find((t) => !isDone(t));
    const trip = nextTask?.trip;
    const rows = trip ? tasks.filter((t) => t.trip === trip) : [];
    return {
        total: tasks.length,
        stores: new Set(tasks.map((t) => t.outlet_id)).size,
        done: tasks.filter(isDone).length,
        nextTask,
        nextTrip: trip
            ? { name: trip, tasks: rows, finished: rows.filter(isDone).length }
            : undefined,
    };
}

/** Tautan navigasi peta eksternal (tanpa membaca lokasi pengguna). */
export const navigationUrl = (latitude: number, longitude: number) =>
    `https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}`;
