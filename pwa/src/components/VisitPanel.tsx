import { useRememberedState, useRememberedScroll } from "../ui/viewMemory";
import { CustomerSummary } from "./CustomerSummary";
import { VisitPhotoField } from "./VisitPhotoField";
import { EvidenceCapture } from "./Evidence";
import { CheckinMap } from "./CheckinMap";
import type { FieldStore } from "../storage/store";
import type { VisitEvidence } from "../domain/visit-contracts";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import { assessVisitFix } from "../domain/visit-validation";
import { captureVisitLocation, type SalesVisits } from "../domain/visits";
import type { VisitFix, VisitCheckout } from "../domain/visit-contracts";
import type { QueueItem } from "../storage/store";
import { Icon } from "./Icon";
export function VisitPanel({
    outlet,
    store,
    owner,
    sessionId,
    service,
    queue,
    changed,
    order,
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
    back: () => void;
}) {
    const [phase, setPhase] = useRememberedState<"checkin" | "open" | "close">(
        `visit-phase:${sessionId}:${outlet.id}`,
        "checkin",
    );
    const previousOrders = useRef(0);
    const panelScroll = useRememberedScroll(
        `visit-scroll:${sessionId}:${outlet.id}`,
    );
    const [info, setInfo] =
        useState<Awaited<ReturnType<SalesVisits["restore"]>>>();
    const [inPhoto, setInPhoto] = useState<VisitEvidence>();
    const [outPhoto, setOutPhoto] = useState<VisitEvidence>();
    const fresh = (photo?: VisitEvidence) =>
        !!photo &&
        (outlet.demo_unrestricted ||
            (Date.now() - Date.parse(photo.capturedAt) <= 60000 &&
                Date.now() >= Date.parse(photo.capturedAt)));
    const [fix, setFix] = useState<VisitFix>();
    const [fixSource, setFixSource] = useState<"device" | "demo">("device");
    const [pinpointSetAt, setPinpointSetAt] = useState(0);
    const [now, setNow] = useState(Date.now());
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [outcome, setOutcome] =
        useState<VisitCheckout["outcome"]>("no_order");
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
                    if (value.orders) setOutcome("order_requested");
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
            setPhase("open");
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
    async function finish(e: SubmitEvent) {
        e.preventDefault();
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
                outcome,
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
        if ((info?.orders ?? 0) > previousOrders.current && phase === "open")
            setPhase("close");
        previousOrders.current = info?.orders ?? 0;
        if (closed) setPhase("close");
    }, [info?.orders, closed, phase]);
    const labels = {
        inside: "Di dalam geofence",
        outside: "Di luar geofence",
        uncertain: "Akurasi belum pasti",
        stale: "Lokasi kedaluwarsa",
        future: "Waktu lokasi tidak valid",
        invalid: "Lokasi tidak valid",
    };
    return (
        <section
            ref={panelScroll}
            class="visit-panel visit-workflow"
            aria-label="Kunjungan outlet"
        >
            <button class="text-button" onClick={back}>
                Kembali ke daftar outlet
            </button>
            <CustomerSummary outlet={outlet} />
            <nav class="workflow-tabs" aria-label="Tahap kunjungan">
                <button
                    aria-pressed={phase === "checkin"}
                    onClick={() => setPhase("checkin")}
                >
                    Check-in toko
                </button>
                <button
                    aria-pressed={phase === "open"}
                    disabled={
                        !active ||
                        closed ||
                        busy ||
                        (!outlet.demo_unrestricted &&
                            assessment?.status !== "inside")
                    }
                    onClick={() => {
                        setPhase("open");
                        order();
                    }}
                >
                    Open session
                </button>
                <button
                    aria-pressed={phase === "close"}
                    disabled={!active && !closed}
                    onClick={() => setPhase("close")}
                >
                    Close session
                </button>
            </nav>
            <p role="status">
                {closed
                    ? "Kunjungan ditutup lokal — menunggu hasil sinkronisasi."
                    : active
                      ? "Kunjungan lokal aktif"
                      : info?.active
                        ? `Masih ada kunjungan aktif: ${info.active.context.outlet_id}`
                        : "Belum check-in kunjungan"}
            </p>
            <div hidden={phase !== "checkin"}>
                {assessment && (
                    <p class="geo-summary" role="status">
                        <strong>{labels[assessment.status]}</strong> · Akurasi ±
                        {Math.round(fix!.accuracy)} m
                    </p>
                )}
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
                <button
                    class="text-button location-retry"
                    onClick={() => void locate()}
                    disabled={busy}
                >
                    <Icon name="pin" size={18} />
                    {busy ? "Memproses lokasi…" : "Perbarui lokasi outlet"}
                </button>
                {!active && !closed && (
                    <VisitPhotoField
                        key={`in:${sessionId}:${outlet.id}`}
                        store={store}
                        owner={owner}
                        sessionId={sessionId}
                        outletId={outlet.id}
                        phase="check_in"
                        ready={setInPhoto}
                        disabled={busy}
                    />
                )}
                {!active && !closed && inPhoto && !fresh(inPhoto) && (
                    <p role="status" class="notice">
                        Foto check-in sudah kedaluwarsa. Ambil foto dan lokasi
                        baru.
                    </p>
                )}
                {!active && !closed && (
                    <button
                        class="primary full"
                        disabled={
                            !info ||
                            !!info.active ||
                            busy ||
                            (!outlet.demo_unrestricted &&
                                !!fix &&
                                assessment?.status !== "inside") ||
                            !fresh(inPhoto)
                        }
                        onClick={() => void start()}
                    >
                        Mulai kunjungan
                    </button>
                )}
            </div>
            <div hidden={phase !== "close"}>
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
                            existingRef={
                                info.selected.check_out.payload.evidence
                            }
                            onChange={() => {}}
                            readOnly
                        />
                    </details>
                )}
            </div>
            {active && !closed && (
                <>
                    <div hidden={phase !== "open"}>
                        <button
                            class="primary full"
                            disabled={
                                busy ||
                                (!outlet.demo_unrestricted &&
                                    assessment?.status !== "inside")
                            }
                            onClick={order}
                        >
                            <Icon name="bag" size={18} /> Buat order di outlet
                        </button>
                    </div>
                    <div hidden={phase !== "close"}>
                        <h3>Ringkasan kunjungan</h3>
                        <p>{info?.orders ?? 0} pengajuan order</p>
                        <button
                            type="button"
                            class="secondary full"
                            style={{ margin: "8px 0 14px" }}
                            disabled={busy}
                            onClick={() => {
                                setPhase("open");
                                order();
                            }}
                        >
                            <Icon name="bag" size={16} /> + Tambah order lagi
                            untuk outlet ini
                        </button>
                        <VisitPhotoField
                            key={`out:${info?.active?.context.visit_uuid}`}
                            store={store}
                            owner={owner}
                            sessionId={sessionId}
                            outletId={outlet.id}
                            phase="check_out"
                            visitId={info?.active?.context.visit_uuid}
                            ready={setOutPhoto}
                            disabled={busy}
                        />
                        {outPhoto && !fresh(outPhoto) && (
                            <p role="status" class="notice">
                                Foto check-out sudah kedaluwarsa. Ambil foto dan
                                lokasi baru.
                            </p>
                        )}
                        <form class="visit-close" onSubmit={finish}>
                            <label>
                                Hasil kunjungan
                                <select
                                    value={
                                        info?.orders
                                            ? "order_requested"
                                            : outcome
                                    }
                                    onChange={(e) =>
                                        setOutcome(
                                            e.currentTarget
                                                .value as VisitCheckout["outcome"],
                                        )
                                    }
                                >
                                    {info?.orders ? (
                                        <option value="order_requested">
                                            Order diajukan
                                        </option>
                                    ) : (
                                        <>
                                            <option value="no_order">
                                                Tidak ada order
                                            </option>
                                            <option value="outlet_closed">
                                                Outlet tutup
                                            </option>
                                            <option value="unavailable">
                                                Kontak tidak tersedia
                                            </option>
                                        </>
                                    )}
                                </select>
                            </label>
                            <label>
                                Catatan kunjungan
                                <textarea
                                    required={!info?.orders}
                                    minLength={info?.orders ? 0 : 5}
                                    maxLength={500}
                                    value={notes}
                                    onInput={(e) =>
                                        setNotes(e.currentTarget.value)
                                    }
                                />
                            </label>
                            <button
                                class="secondary full"
                                type="submit"
                                disabled={busy || !fresh(outPhoto)}
                            >
                                Tutup kunjungan
                            </button>
                        </form>
                    </div>
                </>
            )}
            {error && (
                <p role="alert" class="form-error">
                    {error}
                </p>
            )}
        </section>
    );
}
