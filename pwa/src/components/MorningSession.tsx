import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { Button, Card, CardHead, Chip, DayStep, Callout } from "../ui";
import { SyncProgressCard, type SyncStage } from "./SyncProgressCard";
import type { FieldProvider, Identity } from "../domain/contracts";
import {
    fieldBusinessDate,
    morningReady,
    MorningSimulation,
    type MorningRecord,
} from "../domain/morning";
import type { FieldStore } from "../storage/store";
export function MorningSession({
    identity,
    provider,
    store,
    onChange,
    record: restored,
    loaded,
    restoreError,
    attended,
    onAttend,
    onClockOut,
}: {
    attended: boolean;
    onAttend: () => void;
    onClockOut: () => void;
    record?: MorningRecord;
    loaded: boolean;
    restoreError?: string;
    identity: Identity;
    provider: FieldProvider;
    store: FieldStore;
    onChange: (record: MorningRecord | undefined) => void;
}) {
    const service = useMemo(
        () => new MorningSimulation(store, identity, provider),
        [store, identity, provider],
    );
    const record = restored;
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [stage, setStage] = useState<SyncStage>();
    const [online, setOnline] = useState(navigator.onLine);
    const [date, setDate] = useState(fieldBusinessDate());
    const running = useRef(false);
    const changed = useRef(onChange);
    changed.current = onChange;
    useEffect(() => {
        const net = () => setOnline(navigator.onLine);
        window.addEventListener("online", net);
        window.addEventListener("offline", net);
        const checkDate = () => setDate(fieldBusinessDate());
        const timer = setInterval(checkDate, 15000);
        window.addEventListener("focus", checkDate);
        document.addEventListener("visibilitychange", checkDate);
        return () => {
            clearInterval(timer);
            window.removeEventListener("focus", checkDate);
            document.removeEventListener("visibilitychange", checkDate);
            window.removeEventListener("online", net);
            window.removeEventListener("offline", net);
        };
    }, [service]);
    const today = record?.businessDate === date ? record : undefined;
    const ready =
        morningReady(today, `${identity.companyId}:${identity.id}`, date) &&
        (!identity.roles.includes("delivery") ||
            !!today?.deliveryManifest?.length);
    useEffect(() => {
        if (
            record &&
            !morningReady(record, `${identity.companyId}:${identity.id}`, date)
        )
            changed.current(undefined);
    }, [date]);
    async function advance() {
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        setStage("check");
        try {
            const next = await service.open(setStage);
            changed.current(next);
        } catch (e) {
            setError(
                e instanceof Error
                    ? e.message
                    : "Sesi belum tersimpan. Coba lagi.",
            );
        } finally {
            running.current = false;
            setBusy(false);
            setStage(undefined);
        }
    }
    const clock = (iso?: string) =>
        iso
            ? new Date(iso)
                  .toLocaleTimeString("id-ID", {
                      timeZone: "Asia/Makassar",
                      hour12: false,
                  })
                  .replaceAll(".", ":")
            : "";
    const checkedOut = !!today?.clockOutAt;
    const inTime = clock(today?.attendanceAt);
    return (
        <section
            class="ui-stack"
            aria-label="Sesi kerja"
            data-owner={`${identity.companyId}:${identity.id}`}
            aria-busy={!loaded || busy}
        >
            {attended && today && (
                <Card class="ui-dayrow">
                    <div
                        class="ui-dayrow__main"
                        data-testid="attendance-record"
                    >
                        <div class="ui-dayrow__info">
                            <Chip
                                tone={
                                    checkedOut ? "neu" : ready ? "ok" : "warn"
                                }
                            >
                                {checkedOut
                                    ? "Sesi selesai"
                                    : ready
                                      ? "Sesi aktif"
                                      : "Belum dibuka"}
                            </Chip>
                            <strong class="ui-dayrow__t">
                                Masuk {inTime} WITA
                            </strong>
                            <span class="ui-row__sub">
                                {checkedOut
                                    ? `Pulang ${clock(today.clockOutAt)} WITA`
                                    : ready
                                      ? "Data tersimpan untuk kerja offline"
                                      : `${date} · WITA`}
                            </span>
                        </div>
                        <Button
                            variant="sec"
                            size="md"
                            auto
                            disabled={checkedOut}
                            onClick={onClockOut}
                        >
                            Absen pulang
                        </Button>
                    </div>
                </Card>
            )}
            {!ready && attended && (busy || !!error) && (
                <SyncProgressCard
                    stage={stage}
                    failed={!busy && !!error}
                    online={online}
                    onRetry={() => void advance()}
                />
            )}
            {!ready && !(attended && (busy || !!error)) && (
                <Card>
                    <CardHead title="Mulai hari kerja" />
                    <div class="ui-stack">
                        <DayStep
                            n={1}
                            state={attended ? "done" : "active"}
                            title="Absen masuk"
                            sub={
                                attended
                                    ? `Masuk ${inTime} WITA`
                                    : "Selfie + lokasi di area kantor"
                            }
                            right={
                                attended ? undefined : (
                                    <Chip tone="warn">Wajib</Chip>
                                )
                            }
                        />
                        <DayStep
                            n={2}
                            state={attended ? "active" : "lock"}
                            title="Sinkron data harian"
                            sub="Outlet, produk, harga, tagihan"
                            right={
                                attended ? (
                                    <Chip tone="warn">Wajib</Chip>
                                ) : undefined
                            }
                        />
                        <DayStep
                            n={3}
                            state="lock"
                            title="Mulai kunjungan"
                            sub="Terbuka setelah sync selesai"
                        />
                    </div>
                    {attended ? (
                        <Button
                            icon="sync"
                            disabled={
                                !loaded || busy || !today || !!today.clockOutAt
                            }
                            onClick={() => void advance()}
                        >
                            {busy ? "Memproses…" : "Sinkronkan data harian"}
                        </Button>
                    ) : (
                        <Button icon="camera" onClick={onAttend}>
                            Absen masuk
                        </Button>
                    )}
                </Card>
            )}
            {ready && !checkedOut && (
                <Callout tone="info" icon="check">
                    Paket outlet, stok dan harga tersimpan. Order dapat dibuat
                    offline hari ini.
                </Callout>
            )}
            {(error || restoreError) && (
                <p role="alert" class="form-error">
                    {error || restoreError}
                </p>
            )}
        </section>
    );
}
