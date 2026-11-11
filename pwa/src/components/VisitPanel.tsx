import { VisitPhotoField } from "./VisitPhotoField";
import { CloseVisitScreen } from "./CloseVisitScreen";
import { EvidenceCapture } from "./Evidence";
import { CheckinMap } from "./CheckinMap";
import type { FieldStore } from "../storage/store";
import type { VisitEvidence } from "../domain/visit-contracts";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import { assessVisitFix } from "../domain/visit-validation";
import { useRunningMode } from "../domain/running-mode";
import { captureVisitLocation, type SalesVisits } from "../domain/visits";
import type { VisitFix } from "../domain/visit-contracts";
import type { QueueItem } from "../storage/store";
import {
    ActionCaption,
    Button,
    Callout,
    Card,
    CardHead,
    Chip,
    Field,
    KV,
    ListRow,
    Screen,
    ScreenHeader,
    Tracker,
} from "../ui";
export function VisitPanel({
    outlet,
    store,
    owner,
    sessionId,
    service,
    queue,
    changed,
    order,
    display,
    dialogType,
    finishSignal = 0,
    back,
}: {
    outlet: Snapshot["outlets"][number];
    store: FieldStore;
    owner: string;
    sessionId: string;
    service: SalesVisits;
    queue: QueueItem[];
    changed: () => void;
    order: () => void;
    display: () => void;
    /** Jenis dialog yang sedang terbuka; berubah saat layar Display/Order menutup. */
    dialogType?: string;
    /** Naik setiap kali Hasil kirim meminta lanjut ke Selesai kunjungan. */
    finishSignal?: number;
    back: () => void;
}) {
    const [sheet, setSheet] = useState(false);
    const [displayDone, setDisplayDone] = useState(false);
    useEffect(() => {
        if (finishSignal > 0) setSheet(true);
    }, [finishSignal]);
    useEffect(() => {
        if (dialogType) return;
        let active = true;
        void store
            .draft(owner, `display:${outlet.id}`)
            .then((value) => {
                if (active)
                    setDisplayDone(
                        !!(
                            value &&
                            typeof value === "object" &&
                            (value as { evidence?: unknown }).evidence
                        ),
                    );
            })
            .catch(() => {});
        return () => {
            active = false;
        };
    }, [dialogType, store, owner, outlet.id]);
    const [runningMode] = useRunningMode();
    const isDemo = runningMode === "demo";
    const [info, setInfo] =
        useState<Awaited<ReturnType<SalesVisits["restore"]>>>();
    const [inPhoto, setInPhoto] = useState<VisitEvidence>();
    const [outPhoto, setOutPhoto] = useState<VisitEvidence>();
    const fresh = (photo?: VisitEvidence) =>
        isDemo ||
        (!!photo &&
            (outlet.demo_unrestricted ||
                (Date.now() - Date.parse(photo.capturedAt) <= 60000 &&
                    Date.now() >= Date.parse(photo.capturedAt))));
    const [fix, setFix] = useState<VisitFix>();
    const [fixSource, setFixSource] = useState<"device" | "demo">("device");
    const [pinpointSetAt, setPinpointSetAt] = useState(0);
    const [now, setNow] = useState(Date.now());
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [notes, setNotes] = useState("");
    const running = useRef(false),
        generation = useRef(0);
    useEffect(() => {
        let active = true;
        void service
            .restore(outlet.id)
            .then((value) => {
                if (active) {
                    setInfo(value);
                }
            })
            .catch((e) => {
                if (active) {
                    setInfo(undefined);
                    setError(
                        e instanceof Error
                            ? e.message
                            : "Riwayat kunjungan tidak tersedia.",
                    );
                }
            });
        return () => {
            active = false;
        };
    }, [service, outlet.id, queue]);
    useLayoutEffect(() => {
        const id = setInterval(() => setNow(Date.now()), 5000);
        return () => {
            generation.current++;
            clearInterval(id);
        };
    }, [service, outlet.id]);
    const assessment = fix
        ? assessVisitFix(
              fix,
              {
                  latitude: outlet.latitude,
                  longitude: outlet.longitude,
                  radius: outlet.radius,
              },
              now,
          )
        : undefined;
    // Saving the photo after the pinpoint used to disable "Mulai kunjungan"
    // forever. start() refreshes the fix instead so the documented order holds.
    const active = info?.active?.context.outlet_id === outlet.id;
    const closed = !!info?.selected?.check_out;
    async function locate() {
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setFix(undefined);
        setError("");
        const ticket = generation.current;
        try {
            const position = await captureVisitLocation((source) => {
                if (ticket === generation.current) setFixSource(source);
            });
            if (ticket === generation.current) {
                setFix(position);
                setPinpointSetAt(Date.now());
                setNow(Date.now());
            }
        } catch (e) {
            if (ticket === generation.current)
                setError(
                    e instanceof Error ? e.message : "Lokasi belum tersedia.",
                );
        } finally {
            if (ticket === generation.current) {
                running.current = false;
                setBusy(false);
            }
        }
    }
    useEffect(() => {
        void locate();
    }, [service, outlet.id]);
    async function start() {
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        const ticket = generation.current;
        try {
            // A photo saved after the pinpoint must not lock the visit: capture a
            // fresh fix at the moment of check-in instead of disabling the action.
            const photoAt = inPhoto ? Date.parse(inPhoto.capturedAt) : 0;
            const stale = !fix || pinpointSetAt < photoAt;
            const position = stale
                ? await captureVisitLocation((source) => {
                      if (ticket === generation.current) setFixSource(source);
                  })
                : fix!;
            if (ticket !== generation.current) return;
            setFix(position);
            setPinpointSetAt(Date.now());
            setNow(Date.now());
            await service.checkIn(outlet.id, position, inPhoto);
            if (ticket !== generation.current) return;
            const restored = await service.restore(outlet.id);
            if (ticket !== generation.current) return;
            setInfo(restored);
            changed();
        } catch (e) {
            if (ticket === generation.current)
                setError(
                    e instanceof Error
                        ? e.message
                        : "Check-in belum tersimpan.",
                );
        } finally {
            if (ticket === generation.current) {
                running.current = false;
                setBusy(false);
            }
        }
    }
    async function finish() {
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        const ticket = generation.current;
        try {
            const position = await captureVisitLocation((source) => {
                if (ticket === generation.current) setFixSource(source);
            });
            if (ticket !== generation.current) return;
            setFix(position);
            setNow(Date.now());
            await service.checkOut(
                outlet.id,
                position,
                orders ? "order_requested" : "no_order",
                notes,
                outPhoto,
            );
            const restored = await service.restore(outlet.id);
            if (ticket !== generation.current) return;
            setInfo(restored);
            changed();
        } catch (e) {
            if (ticket === generation.current)
                setError(
                    e instanceof Error
                        ? e.message
                        : "Penutupan belum tersimpan.",
                );
        } finally {
            if (ticket === generation.current) {
                running.current = false;
                setBusy(false);
            }
        }
    }
    useEffect(() => {
        if (closed) setSheet(false);
    }, [closed]);
    const labels = {
        inside: "Di dalam geofence",
        outside: isDemo
            ? "Di luar geofence (diabaikan: mode demo)"
            : "Di luar geofence",
        uncertain: isDemo
            ? "Akurasi belum pasti (diabaikan: mode demo)"
            : "Akurasi belum pasti",
        stale: isDemo
            ? "Lokasi kedaluwarsa (diabaikan: mode demo)"
            : "Lokasi kedaluwarsa",
        future: isDemo
            ? "Waktu tidak valid (diabaikan: mode demo)"
            : "Waktu lokasi tidak valid",
        invalid: "Lokasi tidak valid",
    };
    const canOrder =
        !busy &&
        active &&
        !closed &&
        (isDemo ||
            !!outlet.demo_unrestricted ||
            assessment?.status === "inside");
    const orders = info?.orders ?? 0;
    const commercial = outlet.commercial;
    const idr = new Intl.NumberFormat("id-ID", {
        style: "currency",
        currency: commercial?.currency ?? "IDR",
        maximumFractionDigits: 0,
    });
    const money = (value?: number | null) =>
        value != null ? idr.format(value) : "—";
    const checkinBlocked =
        !info ||
        !!info.active ||
        busy ||
        (!isDemo &&
            !outlet.demo_unrestricted &&
            !!fix &&
            assessment?.status !== "inside") ||
        (!isDemo && !fresh(inPhoto));
    const staleIn = inPhoto && !fresh(inPhoto) && !isDemo;
    const caption = checkinBlocked
        ? !inPhoto
            ? "Foto toko wajib sebelum check-in."
            : staleIn
              ? "Foto check-in sudah kedaluwarsa. Ambil foto dan lokasi baru."
              : assessment && assessment.status !== "inside"
                ? "Check-in hanya sah di dalam area toko."
                : ""
        : "";
    const errorNote = error ? (
        <p role="alert" class="form-error">
            {error}
        </p>
    ) : null;
    if (!active && !closed)
        return (
            <Screen
                label="Kunjungan outlet"
                header={
                    <ScreenHeader
                        title={`Check-in · ${outlet.name}`}
                        onBack={back}
                    />
                }
                footer={
                    <>
                        <Button
                            icon="pin"
                            disabled={checkinBlocked}
                            onClick={() => void start()}
                        >
                            Mulai kunjungan
                        </Button>
                        {caption ? (
                            <ActionCaption>{caption}</ActionCaption>
                        ) : null}
                    </>
                }
            >
                <p role="status" class="ui-visually-hidden">
                    {info?.active
                        ? `Masih ada kunjungan aktif: ${info.active.context.outlet_id}`
                        : "Belum check-in kunjungan"}
                </p>
                {assessment ? (
                    <div class="ui-geo">
                        <Chip
                            tone={
                                assessment.status === "inside" ? "ok" : "warn"
                            }
                            icon={
                                assessment.status === "inside"
                                    ? "check"
                                    : "warning"
                            }
                        >
                            {labels[assessment.status]}
                        </Chip>
                        <span class="ui-row__sub">
                            Akurasi ±{Math.round(fix!.accuracy)} m
                        </span>
                    </div>
                ) : null}
                <CheckinMap
                    key={`${sessionId}:${outlet.id}`}
                    compact
                    site={{
                        name: outlet.name,
                        latitude: outlet.latitude,
                        longitude: outlet.longitude,
                        radius: outlet.radius,
                        simulated: true,
                    }}
                    fix={
                        fix
                            ? { ...fix, simulated: fixSource === "demo" }
                            : undefined
                    }
                />
                <Button
                    variant="sec"
                    size="md"
                    icon="pin"
                    onClick={() => void locate()}
                    disabled={busy}
                >
                    {busy ? "Memproses lokasi…" : "Perbarui lokasi outlet"}
                </Button>
                <Field
                    label="Alamat (otomatis)"
                    value={outlet.address}
                    readOnly
                />
                <VisitPhotoField
                    key={`in:${sessionId}:${outlet.id}`}
                    store={store}
                    owner={owner}
                    sessionId={sessionId}
                    outletId={outlet.id}
                    phase="check_in"
                    ready={setInPhoto}
                    site={{
                        name: outlet.name,
                        latitude: outlet.latitude,
                        longitude: outlet.longitude,
                        radius: outlet.radius,
                    }}
                    disabled={busy}
                />
                {errorNote}
            </Screen>
        );
    return (
        <Screen
            label="Kunjungan outlet"
            header={
                <ScreenHeader
                    title={outlet.name}
                    onBack={back}
                    status={
                        closed
                            ? { tone: "ok", label: "Selesai" }
                            : { tone: "info", label: "Berjalan" }
                    }
                />
            }
            sub={
                <Tracker
                    label="Tahap kunjungan"
                    steps={[
                        { label: "Check-in", state: "done" },
                        {
                            label: "Order",
                            state: closed || orders ? "done" : "cur",
                        },
                        {
                            label: "Selesai",
                            state: closed ? "done" : orders ? "cur" : "future",
                        },
                    ]}
                />
            }
            footer={
                closed ? (
                    <Button variant="sec" onClick={back}>
                        Kembali ke daftar outlet
                    </Button>
                ) : (
                    <>
                        <Button icon="bag" disabled={!canOrder} onClick={order}>
                            Buat order di outlet
                        </Button>
                        <Button
                            variant="sec"
                            disabled={busy}
                            onClick={() => setSheet(true)}
                        >
                            Selesai kunjungan
                        </Button>
                    </>
                )
            }
        >
            <Callout tone={closed ? "neu" : "info"} icon="clock">
                {closed
                    ? "Kunjungan ditutup lokal — menunggu hasil sinkronisasi."
                    : "Kunjungan lokal aktif"}
            </Callout>
            <Card>
                <CardHead title="Profil toko" />
                <span class="ui-row__sub">{outlet.address}</span>
                {[
                    ["Omset terbesar", money(commercial?.max_order)],
                    [
                        "Kunj. sebelumnya",
                        money(commercial?.previous_visit_total),
                    ],
                    ["Top order SKU", commercial?.top_sku ?? "—"],
                    ["TOP", commercial?.payment_terms ?? "—"],
                    ["PIC", commercial?.contact ?? "—"],
                ]
                    .filter(([, value]) => value !== "—")
                    .map(([label, value]) => (
                        <KV key={label} label={label} value={value} />
                    ))}
            </Card>
            <Card>
                <CardHead
                    title="Tagihan jatuh tempo"
                    status={{ tone: "neu", label: "Segera tersedia" }}
                />
                <span class="ui-row__sub">
                    Penagihan di aplikasi belum aktif. Order tidak menunggu
                    tagihan pada versi ini.
                </span>
            </Card>
            <Card tight>
                <ListRow
                    icon="camera"
                    title="Display & stok toko"
                    sub="Foto display wajib sebelum order dikirim"
                    status={
                        displayDone
                            ? { tone: "ok", label: "Tersimpan" }
                            : { tone: "warn", label: "Wajib" }
                    }
                    onClick={canOrder ? display : undefined}
                    divider
                />
                <ListRow
                    icon="bag"
                    title="Order"
                    sub={`${orders} pengajuan order`}
                    status={
                        orders
                            ? { tone: "ok", label: "Diajukan" }
                            : { tone: "info", label: "Siap" }
                    }
                    onClick={canOrder ? order : undefined}
                />
            </Card>
            {info?.selected?.check_in_evidence && (
                <details class="visit-photo-history">
                    <summary>Bukti foto check-in tersimpan</summary>
                    <EvidenceCapture
                        store={store}
                        owner={owner}
                        existingRef={info.selected.check_in_evidence}
                        onChange={() => {}}
                        readOnly
                    />
                </details>
            )}
            {closed && info?.selected?.check_out?.payload.evidence && (
                <details class="visit-photo-history">
                    <summary>Bukti foto check-out tersimpan</summary>
                    <EvidenceCapture
                        store={store}
                        owner={owner}
                        existingRef={info.selected.check_out.payload.evidence}
                        onChange={() => {}}
                        readOnly
                    />
                </details>
            )}
            {errorNote}
            {sheet && !closed && (
                <CloseVisitScreen
                    outlet={outlet}
                    queue={queue}
                    orders={orders}
                    visitId={info?.active?.context.visit_uuid}
                    displayDone={displayDone}
                    notes={notes}
                    setNotes={setNotes}
                    busy={busy}
                    canSubmit={isDemo || fresh(outPhoto)}
                    error={error}
                    onOrder={() => {
                        setSheet(false);
                        order();
                    }}
                    onSubmit={() => void finish()}
                    close={() => setSheet(false)}
                    photoField={
                        <VisitPhotoField
                            key={`out:${info?.active?.context.visit_uuid}`}
                            store={store}
                            owner={owner}
                            sessionId={sessionId}
                            outletId={outlet.id}
                            phase="check_out"
                            visitId={info?.active?.context.visit_uuid}
                            ready={setOutPhoto}
                            site={{
                                name: outlet.name,
                                latitude: outlet.latitude,
                                longitude: outlet.longitude,
                                radius: outlet.radius,
                            }}
                            disabled={busy}
                        />
                    }
                    photoNote={
                        outPhoto && !fresh(outPhoto) && !isDemo
                            ? "Foto check-out sudah kedaluwarsa. Ambil foto dan lokasi baru."
                            : undefined
                    }
                />
            )}
        </Screen>
    );
}
