import {
    TripCloseSchema,
    tripCloseKey,
    DEMO_OFFICE,
} from "./trip-close-contracts";
import {
    MorningRecordSchema,
    morningReady,
    fieldBusinessDate,
} from "./morning";
import { CommandSchema } from "./contracts";
import { assertPodTaskSource, podLineage, validatePodMedia } from "./delivery";
import { distanceMeters } from "./format";
import { EvidenceIntegrityError } from "./evidence-package";
import type { FieldStore, QueueItem } from "../storage/store";
export function tripPods(
    rows: QueueItem[],
    owner: string,
    daily: unknown,
    trip: string,
) {
    const source = MorningRecordSchema.parse(daily),
        tasks = source.deliveryManifest?.filter((t) => t.trip === trip);
    if (!tasks?.length)
        throw new Error("Trip tidak ada di manifest daily sync.");
    if (
        !morningReady(source, owner, source.businessDate) ||
        tasks.some(
            (t) => t.owner !== owner || t.business_date !== source.businessDate,
        ) ||
        new Set(tasks.map((t) => t.id)).size !== tasks.length
    )
        throw new Error("Manifest trip/hari tidak valid; perlu review.");
    return tasks.map((t) => {
        // Reject ambiguous/reused IDs rather than rewriting historic lineage.
        const leaf = podLineage(rows, owner, t.id).at(-1)!;
        assertPodTaskSource(leaf, t, owner);
        return leaf;
    });
}
export function validateTripClose(
    item: QueueItem,
    rows: QueueItem[],
    owner: string,
) {
    if (item.command.type !== "delivery.trip.close")
        throw new Error("DTO closing tidak valid.");
    const p = TripCloseSchema.parse(item.command.payload),
        daily = MorningRecordSchema.parse(p.daily_source);
    if (
        item.owner !== owner ||
        item.key !== `${owner}:${item.command.client_uuid}` ||
        !morningReady(daily, owner, p.business_date) ||
        fieldBusinessDate(new Date(item.command.occurred_at)) !==
            p.business_date ||
        JSON.stringify(p.office) !== JSON.stringify(DEMO_OFFICE)
    )
        throw new Error("Sumber closing kantor tidak sesuai.");
    const expected = tripPods(rows, owner, daily, p.trip_id)
        .map((r) => r.command.client_uuid)
        .sort();
    if (JSON.stringify([...p.pod_uuids].sort()) !== JSON.stringify(expected))
        throw new Error("Trip belum lengkap/POD berubah.");
    const relaxed = daily
        .deliveryManifest!.filter((t) => t.trip === p.trip_id)
        .every((t) => t.site.demo_unrestricted);
    if (!!p.demo_unrestricted !== relaxed)
        throw new Error("Kebijakan closing tidak sesuai sumber.");
    if (
        !(__DEMO__ && p.demo_unrestricted) &&
        (distanceMeters(
            p.fix.latitude,
            p.fix.longitude,
            p.office.latitude,
            p.office.longitude,
        ) +
            p.fix.accuracy >
            p.office.radius + 25 ||
            Date.parse(item.command.occurred_at) -
                Date.parse(p.fix.sampled_at) >
                60000 ||
            Date.parse(p.fix.sampled_at) >
                Date.parse(item.command.occurred_at) + 1000)
    )
        throw new Error("Closing wajib di geofence kantor + toleransi25m.");
    return p;
}
export async function validateTripCloseMedia(
    item: QueueItem,
    owner: string,
    store: FieldStore,
) {
    if (item.command.type !== "delivery.trip.close") return;
    try {
        const rows = await store.list(owner),
            p = validateTripClose(item, rows, owner),
            saved = await store.draft(
                owner,
                tripCloseKey(p.trip_id, p.business_date),
            );
        if (
            JSON.stringify(CommandSchema.parse(saved)) !==
            JSON.stringify(item.command)
        )
            throw new Error("Pointer closing berubah.");
        for (const id of p.pod_uuids) {
            const row = rows.find((r) => r.command.client_uuid === id)!;
            await validatePodMedia(row, owner, store);
        }
        const after = await store.list(owner);
        validateTripClose(item, after, owner);
        if (
            JSON.stringify(
                await store.draft(
                    owner,
                    tripCloseKey(p.trip_id, p.business_date),
                ),
            ) !== JSON.stringify(saved)
        )
            throw new Error("Closing berubah saat baca bukti.");
    } catch {
        throw new EvidenceIntegrityError("Closing/sumber trip perlu review.");
    }
}
