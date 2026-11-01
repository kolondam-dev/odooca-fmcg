import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { FieldProvider, Identity } from "../domain/contracts";
import {
    fieldBusinessDate,
    morningReady,
    MorningSimulation,
    type MorningRecord,
} from "../domain/morning";
import type { FieldStore } from "../storage/store";
import { Icon } from "./Icon";
export function MorningSession({
    identity,
    provider,
    store,
    onChange,
    record: restored,
    loaded,
    restoreError,
}: {
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
    const [date, setDate] = useState(fieldBusinessDate());
    const running = useRef(false);
    const changed = useRef(onChange);
    changed.current = onChange;
    useEffect(() => {
        const checkDate = () => setDate(fieldBusinessDate());
        const timer = setInterval(checkDate, 15000);
        window.addEventListener("focus", checkDate);
        document.addEventListener("visibilitychange", checkDate);
        return () => {
            clearInterval(timer);
            window.removeEventListener("focus", checkDate);
            document.removeEventListener("visibilitychange", checkDate);
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
        try {
            const next = await service.open();
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
        }
    }
    return (
        <section
            class="morning-card"
            aria-label="Sesi kerja"
            data-owner={`${identity.companyId}:${identity.id}`}
            aria-busy={!loaded || busy}
        >
            <div class="morning-heading">
                <Icon name={ready ? "check" : "clock"} />
                <div>
                    <h2>Sesi kerja</h2>
                    <p>
                        {date} · WITA
                        {ready && today?.snapshot?.version
                            ? ` · ${today.snapshot.version}`
                            : ""}
                    </p>
                </div>
                <span class={`pill ${ready ? "success" : "neutral"}`}>
                    {today?.clockOutAt
                        ? "Sesi selesai"
                        : ready
                          ? "Sesi aktif"
                          : "Belum dibuka"}
                </span>
            </div>
            {ready ? (
                <p class="notice" role="status">
                    Paket outlet, stok dan harga tersimpan. Order dapat dibuat
                    offline hari ini.
                </p>
            ) : (
                <button
                    class="secondary full"
                    disabled={!loaded || busy || !today || !!today.clockOutAt}
                    onClick={() => void advance()}
                >
                    {busy ? "Memproses…" : "Buka sesi kerja"}
                </button>
            )}
            {(error || restoreError) && (
                <p role="alert" class="form-error">
                    {error || restoreError}
                </p>
            )}
        </section>
    );
}
