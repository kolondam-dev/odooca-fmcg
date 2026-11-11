import { useEffect, useState } from "preact/hooks";
import {
    Button,
    Callout,
    Card,
    CardHead,
    ListRow,
    Screen,
    ScreenHeader,
    Textarea,
} from "../ui";
import { tripMoney } from "../domain/trip-summary";
import { useBackLayer } from "../ui/navigation";
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
const rupiah = (n: number) => `Rp ${Math.round(n).toLocaleString("id-ID")}`;
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
        [busy, setBusy] = useState(false),
        [open, setOpen] = useState<string>(),
        [note, setNote] = useState("");
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
        const closingNote = note.trim();
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
                    ...(closingNote ? { note: closingNote } : {}),
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
                `Trip closed lokal. Jarak kantor contoh ${Math.round(distanceMeters(fix.latitude, fix.longitude, DEMO_OFFICE.latitude, DEMO_OFFICE.longitude))}m; toleransi25m. Tanpa validasi lokasi kantor. Belum settlement kasir/Odoo.`,
            );
            changed();
            void engine.flush();
        } catch (e) {
            setMessage(e instanceof Error ? e.message : "Closing gagal.");
        } finally {
            setBusy(false);
        }
    }
    const businessDate = morning?.businessDate;
    const cash = (trip: string) =>
        tripMoney(queue, owner, businessDate, trip).cash;
    const transfer = (trip: string) =>
        tripMoney(queue, owner, businessDate, trip).transfer;
    const tripCost = (trip: string) =>
        tripMoney(queue, owner, businessDate, trip).cost;
    const podCount = (trip: string) =>
        morning?.deliveryManifest?.filter((t) => t.trip === trip).length ?? 0;
    useBackLayer(!!open, () => setOpen(undefined));
    if (!trips.length) return null;
    return (
        <>
            <Card>
                <CardHead title="Akhiri trip" />
                {trips.map((trip) => (
                    <ListRow
                        key={trip}
                        icon="truck"
                        title={trip}
                        sub={`${podCount(trip)} pengiriman · tutup setelah semua DO selesai`}
                        status={
                            closed[trip]
                                ? { tone: "ok", label: "Closed lokal" }
                                : { tone: "info", label: "Belum ditutup" }
                        }
                        onClick={() => setOpen(trip)}
                        divider
                    />
                ))}
            </Card>
            {open ? (
                <Screen
                    label={`Akhiri trip · ${open}`}
                    class="ui-screen--over ui-screen--top"
                    header={
                        <ScreenHeader
                            title={`Akhiri trip · ${open}`}
                            onBack={() => setOpen(undefined)}
                        />
                    }
                    footer={
                        closed[open] ? (
                            <Button
                                variant="sec"
                                onClick={() => setOpen(undefined)}
                            >
                                Kembali
                            </Button>
                        ) : (
                            <Button
                                icon="check"
                                disabled={busy}
                                onClick={() => void close(open)}
                            >
                                {busy ? "Menyimpan…" : "Akhiri trip"}
                            </Button>
                        )
                    }
                >
                    <Card tight>
                        <ListRow
                            icon="truck"
                            title="Pengiriman"
                            sub={`${podCount(open)} DO di trip ini`}
                            status={
                                closed[open]
                                    ? { tone: "ok", label: "Selesai" }
                                    : {
                                          tone: "neu",
                                          label: "Dicek saat akhiri",
                                      }
                            }
                        />
                        <ListRow
                            icon="wallet"
                            title="Penerimaan uang"
                            sub="Tunai + transfer trip ini (lokal, tidak ditolak)"
                            status={{
                                tone: "info",
                                label: rupiah(cash(open) + transfer(open)),
                            }}
                            divider
                        />
                        <ListRow
                            icon="receipt"
                            title="Biaya trip"
                            sub="Pengajuan uang lapangan trip ini"
                            status={{
                                tone: "info",
                                label: rupiah(tripCost(open)),
                            }}
                            divider
                        />
                        <ListRow
                            icon="pin"
                            title="Tiba di kantor"
                            sub="Lokasi dicatat saat Akhiri trip"
                            status={
                                closed[open]
                                    ? { tone: "ok", label: "OK" }
                                    : { tone: "neu", label: "Belum" }
                            }
                            divider
                        />
                    </Card>
                    {!closed[open] ? (
                        <Textarea
                            label="Catatan penutupan (opsional)"
                            value={note}
                            onInput={setNote}
                            maxLength={500}
                        />
                    ) : null}
                    {message ? (
                        <Callout tone={closed[open] ? "info" : "warn"} alert>
                            {message}
                        </Callout>
                    ) : null}
                    <Callout tone="neu">
                        Serah-terima kasir di luar scope PWA. Backlog: upload
                        resi uang/cek ke kasir, faktur ke admin, retur ke SPV
                        gudang.
                    </Callout>
                </Screen>
            ) : null}
        </>
    );
}
