import { useEffect, useRef, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import { assessVisitFix } from "../domain/visit-validation";
import { captureVisitLocation, type SalesVisits } from "../domain/visits";
import type { VisitFix, VisitCheckout } from "../domain/visit-contracts";
import type { QueueItem } from "../storage/store";
import { Icon } from "./Icon";
export function VisitPanel({
    outlet,
    service,
    queue,
    changed,
    order,
    back,
}: {
    outlet: Snapshot["outlets"][number];
    service: SalesVisits;
    queue: QueueItem[];
    changed: () => void;
    order: () => void;
    back: () => void;
}) {
    const [info, setInfo] =
        useState<Awaited<ReturnType<SalesVisits["restore"]>>>();
    const [fix, setFix] = useState<VisitFix>();
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
    useEffect(() => {
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
            const position = await captureVisitLocation();
            if (ticket === generation.current) {
                setFix(position);
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
    async function start() {
        if (running.current || !fix) return;
        running.current = true;
        setBusy(true);
        setError("");
        try {
            await service.checkIn(outlet.id, fix);
            setInfo(await service.restore(outlet.id));
            changed();
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Check-in belum tersimpan.",
            );
        } finally {
            running.current = false;
            setBusy(false);
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
            const position = await captureVisitLocation();
            if (ticket !== generation.current) return;
            setFix(position);
            setNow(Date.now());
            await service.checkOut(outlet.id, position, outcome, notes);
            setInfo(await service.restore(outlet.id));
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
    const labels = {
        inside: "Di dalam geofence",
        outside: "Di luar geofence",
        uncertain: "Akurasi belum pasti",
        stale: "Lokasi kedaluwarsa",
        future: "Waktu lokasi tidak valid",
        invalid: "Lokasi tidak valid",
    };
    return (
        <section class="visit-panel paper-card" aria-label="Kunjungan outlet">
            <button class="text-button" onClick={back}>
                Kembali ke daftar outlet
            </button>
            <h2>{outlet.name}</h2>
            <p>{outlet.address}</p>
            <p class="notice">
                SIMULASI · Radius {outlet.radius} m dari paket PJP pagi. Jarak +
                akurasi harus tetap di dalam radius.
            </p>
            <p role="status">
                {closed
                    ? "Kunjungan ditutup lokal — menunggu hasil sinkronisasi."
                    : active
                      ? "Kunjungan lokal aktif"
                      : info?.active
                        ? `Masih ada kunjungan aktif: ${info.active.context.outlet_id}`
                        : "Belum check-in kunjungan"}
            </p>
            <button
                class="secondary full"
                onClick={() => void locate()}
                disabled={busy}
            >
                <Icon name="pin" size={18} />
                {busy ? "Memproses lokasi…" : "Ambil lokasi outlet"}
            </button>
            {assessment && (
                <div class="geo-assessment" role="status">
                    <strong>{labels[assessment.status]}</strong>
                    <p>
                        {Number.isFinite(assessment.distance)
                            ? `Jarak ${assessment.distance.toFixed(1)} m · `
                            : ""}
                        Akurasi ±{fix!.accuracy.toFixed(1)} m
                    </p>
                    <small>
                        {fix!.latitude.toFixed(6)}, {fix!.longitude.toFixed(6)}{" "}
                        ·{" "}
                        {new Date(fix!.sampled_at).toLocaleTimeString("id-ID", {
                            timeZone: "Asia/Makassar",
                        })}{" "}
                        WITA
                    </small>
                </div>
            )}
            {!active && !closed && (
                <button
                    class="primary full"
                    disabled={
                        !info ||
                        !!info.active ||
                        busy ||
                        assessment?.status !== "inside"
                    }
                    onClick={() => void start()}
                >
                    Mulai kunjungan demo
                </button>
            )}
            {active && !closed && (
                <>
                    <button
                        class="primary full"
                        disabled={busy || assessment?.status !== "inside"}
                        onClick={order}
                    >
                        <Icon name="bag" size={18} /> Buat order di outlet
                    </button>
                    <form class="visit-close" onSubmit={finish}>
                        <label>
                            Hasil kunjungan
                            <select
                                value={
                                    info?.orders ? "order_requested" : outcome
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
                                        Pengajuan order dibuat (belum tentu
                                        diterima)
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
                                onInput={(e) => setNotes(e.currentTarget.value)}
                            />
                        </label>
                        <button
                            class="secondary full"
                            type="submit"
                            disabled={busy}
                        >
                            Tutup kunjungan demo
                        </button>
                    </form>
                </>
            )}
            {error && (
                <p role="alert" class="form-error">
                    {error}
                </p>
            )}
            <p class="footnote">
                Koordinat outlet dan sesi masih contoh. Geolocation browser
                tidak membuktikan bebas mock GPS. Verifikasi lokasi/otorisasi
                resmi menunggu backend; tidak ada polling lokasi latar belakang.
            </p>
        </section>
    );
}
