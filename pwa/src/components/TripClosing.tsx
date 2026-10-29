import { useEffect, useState } from "preact/hooks";
import {
    TripCloseSchema,
    DEMO_OFFICE,
    tripCloseKey,
} from "../domain/trip-close-contracts";
import { tripPods, validateTripCloseMedia } from "../domain/trip-close";
import { validatePodMedia } from "../domain/delivery";
import { captureVisitLocation } from "../domain/visits";
import { distanceMeters } from "../domain/format";
import {
    MORNING_KEY,
    morningReady,
    type MorningRecord,
} from "../domain/morning";
import { CommandSchema, ownerKey, type Identity } from "../domain/contracts";
import type { FieldStore, QueueItem } from "../storage/store";
import type { Outbox } from "../domain/outbox";
export function TripClosing({
    store,
    identity,
    morning,
    queue,
    engine,
    changed,
}: {
    store: FieldStore;
    identity: Identity;
    morning?: MorningRecord;
    queue: QueueItem[];
    engine: Outbox;
    changed: () => void;
}) {
    const owner = ownerKey(identity),
        trips = [
            ...new Set(morning?.deliveryManifest?.map((t) => t.trip) ?? []),
        ];
    const [message, setMessage] = useState(""),
        [busy, setBusy] = useState(false);
    const [closed, setClosed] = useState<Record<string, boolean>>({});
    useEffect(() => {
        let active = true;
        void Promise.all(
            trips.map(async (trip) => {
                const saved = await store.draft(
                    owner,
                    tripCloseKey(trip, identity.businessDate),
                );
                if (saved === undefined) return [trip, false] as const;
                const command = CommandSchema.parse(saved);
                if (
                    command.type !== "delivery.trip.close" ||
                    command.payload.trip_id !== trip ||
                    command.payload.business_date !== identity.businessDate
                )
                    throw new Error("Pointer closing berbeda trip/hari.");
                const row = (await store.list(owner)).find(
                    (r) => r.command.client_uuid === command.client_uuid,
                );
                if (
                    !row ||
                    JSON.stringify(row.command) !== JSON.stringify(command)
                )
                    throw new Error("Closing kehilangan antrean.");
                await validateTripCloseMedia(row, owner, store);
                return [trip, true] as const;
            }),
        )
            .then((pairs) => {
                if (active) setClosed(Object.fromEntries(pairs));
            })
            .catch(() => {
                if (active) {
                    setClosed({});
                    setMessage(
                        "Status closing tidak valid; perlu review. Data dipertahankan.",
                    );
                }
            });
        return () => {
            active = false;
        };
    }, [owner, morning, queue]);
    async function close(trip: string) {
        setBusy(true);
        setMessage("");
        try {
            const daily = (await store.draft(
                owner,
                MORNING_KEY,
            )) as MorningRecord;
            if (!morningReady(daily, owner))
                throw new Error("Daily sync wajib sebelum closing.");
            const rows = await store.list(owner),
                pods = tripPods(rows, owner, daily, trip);
            for (const row of pods) await validatePodMedia(row, owner, store);
            const fix = await captureVisitLocation(),
                p = TripCloseSchema.parse({
                    trip_id: trip,
                    business_date: daily.businessDate,
                    daily_source: daily,
                    office: DEMO_OFFICE,
                    fix,
                    pod_uuids: pods.map((r) => r.command.client_uuid).sort(),
                    ...(daily
                        .deliveryManifest!.filter((t) => t.trip === trip)
                        .every((t) => t.site.demo_unrestricted)
                        ? { demo_unrestricted: true }
                        : {}),
                });
            const uuid = crypto.randomUUID(),
                at = new Date().toISOString();
            await engine.enqueue(
                "delivery.trip.close",
                p,
                `Closing trip • ${trip}`,
                uuid,
                {
                    key: tripCloseKey(trip, daily.businessDate),
                    expected: undefined,
                    value: {
                        schema_version: 1,
                        client_uuid: uuid,
                        occurred_at: at,
                        type: "delivery.trip.close",
                        payload: p,
                    },
                    occurredAt: at,
                },
            );
            setClosed((v) => ({ ...v, [trip]: true }));
            setMessage(
                `Trip closed lokal. Jarak kantor contoh ${Math.round(distanceMeters(fix.latitude, fix.longitude, DEMO_OFFICE.latitude, DEMO_OFFICE.longitude))}m; toleransi25m. Demo tanpa validasi lokasi. Belum settlement kasir/Odoo.`,
            );
            changed();
            void engine.flush();
        } catch (e) {
            setMessage(e instanceof Error ? e.message : "Closing gagal.");
        } finally {
            setBusy(false);
        }
    }
    if (!trips.length) return null;
    return (
        <section class="paper-card">
            <h3>Closing trip · tiba di kantor</h3>
            <p>
                Kantor contoh radius30m + toleransi25m. Aturan geofence
                disimpan, tidak memblokir demo tanpa validasi lokasi. Selesaikan
                semua hasil DO dan tutup sesi aktif dahulu; pending approval
                boleh tercatat, bukan dianggap disetujui.
            </p>
            {trips.map((trip) => (
                <p key={trip}>
                    {trip} ·{" "}
                    {closed[trip] ? (
                        "Trip closed lokal"
                    ) : (
                        <button
                            class="secondary"
                            disabled={busy}
                            onClick={() => void close(trip)}
                        >
                            Tutup trip demo
                        </button>
                    )}
                </p>
            ))}
            <p>
                Serah-terima kasir di luar scope PWA. Backlog: upload resi
                uang/cek ke kasir, faktur ke admin, retur ke SPV gudang.
            </p>
            {message && <p role="status">{message}</p>}
        </section>
    );
}
