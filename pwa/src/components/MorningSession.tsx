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
}: {
    identity: Identity;
    provider: FieldProvider;
    store: FieldStore;
    onChange: (record: MorningRecord | undefined) => void;
}) {
    const service = useMemo(
        () => new MorningSimulation(store, identity, provider),
        [store, identity, provider],
    );
    const [record, setRecord] = useState<MorningRecord>();
    const [loaded, setLoaded] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [date, setDate] = useState(fieldBusinessDate());
    const running = useRef(false);
    const changed = useRef(onChange);
    changed.current = onChange;
    useEffect(() => {
        let active = true;
        void service
            .restore()
            .then((value) => {
                if (active) {
                    setRecord(value);
                    changed.current(value);
                    setLoaded(true);
                }
            })
            .catch(() => {
                if (active) {
                    setError(
                        "Penyimpanan sesi tidak tersedia. Kunjungan tetap terkunci.",
                    );
                    setLoaded(true);
                }
            });
        const checkDate = () => setDate(fieldBusinessDate());
        const timer = setInterval(checkDate, 15000);
        window.addEventListener("focus", checkDate);
        document.addEventListener("visibilitychange", checkDate);
        return () => {
            active = false;
            clearInterval(timer);
            window.removeEventListener("focus", checkDate);
            document.removeEventListener("visibilitychange", checkDate);
        };
    }, [service]);
    const today = record?.businessDate === date ? record : undefined;
    const ready = morningReady(
        today,
        `${identity.companyId}:${identity.id}`,
        date,
    );
    async function advance() {
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        try {
            const next = today
                ? await service.open()
                : await service.acceptAttendance();
            setRecord(next);
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
        <section class="morning-card" aria-label="Sesi kerja pagi simulasi">
            <div class="morning-heading">
                <Icon name={ready ? "check" : "clock"} />
                <div>
                    <h2>Sesi kerja pagi</h2>
                    <p>SIMULASI · {date} · WITA</p>
                </div>
                <span class={`pill ${ready ? "success" : "neutral"}`}>
                    {ready ? "Sesi terbuka" : "Belum siap"}
                </span>
            </div>
            <ol class="morning-steps">
                <li>{today ? "✓" : "1."} Absensi diterima simulator</li>
                <li>{ready ? "✓" : "2."} Sync online PJP, stok & harga</li>
                <li>{ready ? "✓" : "3."} Kunjungan & order dapat diantrekan</li>
            </ol>
            <p class="footnote">
                Kontrol demo ini menggantikan respons absensi untuk menguji
                alur. Bukan absensi sah, login atau persetujuan Odoo.
            </p>
            {ready ? (
                <p class="notice" role="status">
                    Paket pagi {today?.snapshot?.version} tersimpan. Order dapat
                    dibuat offline hari ini.
                </p>
            ) : (
                <button
                    class="secondary full"
                    disabled={!loaded || busy}
                    onClick={() => void advance()}
                >
                    {busy
                        ? "Memproses…"
                        : today
                          ? "Sync pagi & buka sesi demo"
                          : "Simulasikan absensi diterima"}
                </button>
            )}
            {error && (
                <p role="alert" class="form-error">
                    {error}
                </p>
            )}
        </section>
    );
}
