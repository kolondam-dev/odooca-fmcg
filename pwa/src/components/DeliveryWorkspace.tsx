import { useEffect, useState } from "preact/hooks";
import { z } from "zod";
import {
    MORNING_KEY,
    morningReady,
    type MorningRecord,
} from "../domain/morning";
import {
    DeliveryTaskSchema,
    podKey,
    type DeliveryTask,
} from "../domain/delivery-contracts";
import type { Outbox } from "../domain/outbox";
import type { FieldStore, QueueItem } from "../storage/store";
import {
    ownerKey,
    type Identity,
    type FieldProvider,
} from "../domain/contracts";
import { DeliveryTaskEditor } from "./DeliveryTaskEditor";
import type { ExpenseSubmit } from "./BiayaTokoScreen";
import type { Snapshot } from "../domain/contracts";
import { businessRejected } from "../domain/outbox-state";
import { useBackLayer } from "../ui/navigation";
import {
    Button,
    Callout,
    Card,
    CardHead,
    Progress,
    Screen,
    ScreenHeader,
} from "../ui";
import { Icon } from "./Icon";
export function DeliveryWorkspace({
    store,
    identity,
    engine,
    changed,
    queue,
    snapshot,
    submit,
}: {
    store: FieldStore;
    identity: Identity;
    provider: FieldProvider;
    engine: Outbox;
    changed: () => void;
    queue: QueueItem[];
    snapshot: Snapshot;
    submit: ExpenseSubmit;
}) {
    const owner = ownerKey(identity),
        cache = `delivery-manifest-v1:${identity.businessDate}`;
    const [tasks, setTasks] = useState<DeliveryTask[]>(),
        [error, setError] = useState(""),
        [tripOpen, setTripOpen] = useState<string>(),
        [taskOpen, setTaskOpen] = useState<string>();
    useEffect(() => {
        let active = true;
        void (async () => {
            const morning = (await store.draft(owner, MORNING_KEY)) as
                | MorningRecord
                | undefined;
            if (!morningReady(morning, owner) || !morning?.deliveryManifest)
                throw new Error(
                    "Daily sync manifest wajib sebelum list Delivery.",
                );
            const manifest = z
                .array(DeliveryTaskSchema)
                .min(1)
                .parse(morning.deliveryManifest);
            if (
                manifest.some(
                    (s) =>
                        s.owner !== owner ||
                        s.business_date !== identity.businessDate,
                ) ||
                new Set(manifest.map(podKey)).size !== manifest.length
            )
                throw new Error(
                    "Manifest tidak cocok dengan petugas/hari ini.",
                );
            let value = await store.draft(owner, cache);
            if (value === undefined) {
                // Daily sync already fetched this bundle. No network is needed to
                // materialize the validated local projection for the first visit.
                value = await store.createDraftIfAbsent(owner, cache, manifest);
            }
            const parsed = z.array(DeliveryTaskSchema).min(1).parse(value);
            if (JSON.stringify(parsed) !== JSON.stringify(manifest))
                throw new Error(
                    "Manifest tidak cocok dengan petugas/hari ini.",
                );
            if (active) setTasks(parsed);
        })().catch((e) => {
            if (active) setError(e.message);
        });
        return () => {
            active = false;
        };
    }, [owner, cache]);
    /**
     * DO selesai hanya bila ada POD di antrean yang bersumber manifest sama (bukan sisa hari/manifest lain)
     * dan tidak ditolak server. POD ditolak masih butuh koreksi; koreksi valid (anak) baru menghitung selesai.
     */
    const sources = new Set(
        queue.flatMap((r) =>
            r.command.type === "delivery.pod.submit" && !businessRejected(r)
                ? [JSON.stringify(r.command.payload.source)]
                : [],
        ),
    );
    const isDone = (t: DeliveryTask) => sources.has(JSON.stringify(t));
    const trips = [...new Set((tasks ?? []).map((t) => t.trip))];
    const openTrip = tripOpen
        ? tasks?.filter((t) => t.trip === tripOpen)
        : undefined;
    const openTask = tasks?.find((t) => podKey(t) === taskOpen);
    const next = openTrip?.find((t) => !isDone(t));
    return (
        <section aria-label="Delivery order hari ini">
            {tasks?.[0] ? (
                <p class="ui-sub">
                    {identity.name} · {tasks[0].vehicle}
                </p>
            ) : null}
            <h2 class="ui-h2">Delivery order hari ini</h2>
            {error && (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            )}
            {trips.map((trip) => {
                const rows = tasks!.filter((t) => t.trip === trip);
                const finished = rows.filter(isDone).length;
                const status =
                    finished === rows.length
                        ? { tone: "ok" as const, label: "Selesai" }
                        : finished
                          ? { tone: "info" as const, label: "Berjalan" }
                          : { tone: "neu" as const, label: "Belum mulai" };
                return (
                    <button
                        type="button"
                        key={trip}
                        class="ui-card ui-card--press"
                        aria-label={`Buka ${trip}`}
                        onClick={() => setTripOpen(trip)}
                    >
                        <CardHead title={trip} status={status} />
                        <p class="ui-sub">
                            {rows.length} toko · {rows[0].vehicle}
                        </p>
                        <Progress
                            label={`Kemajuan ${trip}`}
                            value={(finished / rows.length) * 100}
                        />
                        <p class="ui-sub">
                            {finished}/{rows.length} toko selesai
                        </p>
                    </button>
                );
            })}
            {openTrip ? (
                <TripStores
                    trip={tripOpen!}
                    rows={openTrip}
                    isDone={isDone}
                    next={next}
                    open={(t) => setTaskOpen(podKey(t))}
                    close={() => setTripOpen(undefined)}
                />
            ) : null}
            {openTask ? (
                <DeliveryTaskEditor
                    key={JSON.stringify(openTask)}
                    task={openTask}
                    {...{
                        store,
                        owner,
                        engine,
                        changed,
                        queue,
                        snapshot,
                        submit,
                    }}
                    close={() => setTaskOpen(undefined)}
                />
            ) : null}
        </section>
    );
}
/** Daftar toko dalam satu DO (DS: Delivery_detail). */
function TripStores({
    trip,
    rows,
    isDone,
    next,
    open,
    close,
}: {
    trip: string;
    rows: DeliveryTask[];
    isDone: (t: DeliveryTask) => boolean;
    next?: DeliveryTask;
    open: (t: DeliveryTask) => void;
    close: () => void;
}) {
    useBackLayer(true, close);
    return (
        <Screen
            label={`Daftar toko ${trip}`}
            class="ui-screen--over"
            header={<ScreenHeader title={trip} onBack={close} />}
            footer={
                next ? (
                    <Button icon="pin" onClick={() => open(next)}>
                        Check-in toko · {next.outlet}
                    </Button>
                ) : undefined
            }
        >
            {rows.map((t) => {
                const status = isDone(t)
                    ? { tone: "ok" as const, label: "Selesai" }
                    : t === next
                      ? { tone: "info" as const, label: "Berikutnya" }
                      : { tone: "neu" as const, label: "Belum" };
                return (
                    <Card key={podKey(t)}>
                        <CardHead title={t.outlet} status={status} />
                        <p class="ui-sub">{t.address}</p>
                        <p class="ui-sub">
                            <Icon name="truck" size={18} /> Drop:{" "}
                            {t.lines
                                .map((l) => `${l.quantity} ${l.unit}`)
                                .join(", ")}
                        </p>
                        <div class="ui-row-actions">
                            <Button
                                variant="sec"
                                size="md"
                                icon="arrow"
                                onClick={() =>
                                    window.open(
                                        `https://www.google.com/maps/dir/?api=1&destination=${t.site.latitude},${t.site.longitude}`,
                                        "_blank",
                                        "noopener",
                                    )
                                }
                            >
                                Navigasi
                            </Button>
                            <Button
                                variant="sec"
                                size="md"
                                aria-label={`Buka ${t.id}`}
                                onClick={() => open(t)}
                            >
                                {t.id}
                            </Button>
                        </div>
                    </Card>
                );
            })}
        </Screen>
    );
}
