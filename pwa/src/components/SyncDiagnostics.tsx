import { useEffect, useState } from "preact/hooks";
import {
    diagnoseSync,
    type QueueFilter,
    type SyncSnapshot,
} from "../domain/sync-diagnostics";
import type { FieldStore, QueueItem } from "../storage/store";
import { Icon } from "./Icon";
const filters: [QueueFilter, string][] = [
    ["all", "Semua"],
    ["pending", "Menunggu"],
    ["review", "Perlu review"],
    ["approval", "Approval"],
    ["accepted", "Diterima"],
];
const timestamp = (value?: string) =>
    value
        ? new Date(value).toLocaleString("id-ID", {
              timeZone: "Asia/Makassar",
              dateStyle: "medium",
              timeStyle: "short",
          }) + " WITA"
        : "Waktu tidak valid";
export function SyncDiagnostics({
    store,
    owner,
    queue,
    online,
}: {
    store: FieldStore;
    owner: string;
    queue: QueueItem[];
    online: boolean;
}) {
    const [snapshot, setSnapshot] = useState<SyncSnapshot>();
    const [error, setError] = useState("");
    const [filter, setFilter] = useState<QueueFilter>("all");
    const [now, setNow] = useState(Date.now());
    useEffect(() => {
        let active = true;
        setError("");
        void store
            .visitSyncState(owner)
            .then((value) => {
                if (active) {
                    setSnapshot(value);
                    setNow(Date.now());
                }
            })
            .catch(() => {
                if (active)
                    setError(
                        "Diagnosis tidak tersedia. Data lokal tidak dihapus. Coba buka layar ini kembali.",
                    );
            });
        return () => {
            active = false;
        };
    }, [store, owner, queue]);
    const rows = snapshot ? diagnoseSync(snapshot, owner, online, now) : [];
    const visible = rows.filter(
        (row) => filter === "all" || row.group === filter,
    );
    return (
        <section class="sync-diagnostics" aria-label="Diagnosis sinkronisasi">
            <p class="footnote">
                Diagnosis lokal. Membuka detail tidak mengirim atau mengubah
                transaksi.
            </p>
            <div class="queue-filters" role="group" aria-label="Filter antrean">
                {filters.map(([id, label]) => (
                    <button
                        key={id}
                        class="queue-filter"
                        aria-pressed={filter === id}
                        onClick={() => {
                            setFilter(id);
                            setNow(Date.now());
                        }}
                    >
                        {label}{" "}
                        <span>
                            {id === "all"
                                ? rows.length
                                : rows.filter((r) => r.group === id).length}
                        </span>
                    </button>
                ))}
            </div>
            {error ? (
                <p role="alert" class="form-error">
                    {error}
                </p>
            ) : !snapshot ? (
                <p role="status">Memuat diagnosis lokal…</p>
            ) : !rows.length ? (
                <p class="empty-state">
                    Belum ada aktivitas. Mulai dari order atau pengajuan.
                </p>
            ) : !visible.length ? (
                <p role="status">Tidak ada transaksi pada filter ini.</p>
            ) : (
                <div class="activity-list">
                    {visible.map((row) => (
                        <article class="activity" key={row.key}>
                            <span class={`activity-dot ${row.state}`} />
                            <div class="queue-item">
                                <strong>{row.label}</strong>
                                <small>
                                    {timestamp(row.occurredAt)} ·{" "}
                                    {row.uuid.slice(0, 8)}
                                </small>
                                <p>{row.message}</p>
                                <span
                                    class={`pill ${row.group === "review" ? "red" : row.state === "accepted" ? "green" : "amber"}`}
                                >
                                    {row.stateLabel}
                                </span>
                                <p class="queue-reason">{row.title}</p>
                                <details class="queue-details">
                                    <summary>
                                        <Icon
                                            name={
                                                row.group === "review"
                                                    ? "warning"
                                                    : "receipt"
                                            }
                                            size={18}
                                        />{" "}
                                        Detail sinkronisasi
                                    </summary>
                                    <p>{row.guidance}</p>
                                    <dl>
                                        <dt>UUID transaksi</dt>
                                        <dd>{row.uuid}</dd>
                                        <dt>Jenis transaksi</dt>
                                        <dd>{row.type}</dd>
                                        <dt>Waktu aksi</dt>
                                        <dd>{timestamp(row.occurredAt)}</dd>
                                        <dt>Percobaan kirim</dt>
                                        <dd>{row.attempts}</dd>
                                        {row.reference && (
                                            <>
                                                <dt>Referensi receipt</dt>
                                                <dd>{row.reference}</dd>
                                            </>
                                        )}
                                        {row.retryAt && (
                                            <>
                                                <dt>Jadwal coba ulang</dt>
                                                <dd>
                                                    {timestamp(row.retryAt)}
                                                </dd>
                                            </>
                                        )}
                                        {row.context && (
                                            <>
                                                <dt>Sesi kerja</dt>
                                                <dd>{row.context.session}</dd>
                                                <dt>Tanggal bisnis</dt>
                                                <dd>{row.context.date}</dd>
                                                <dt>Outlet</dt>
                                                <dd>{row.context.outlet}</dd>
                                                <dt>Versi paket pagi</dt>
                                                <dd>{row.context.version}</dd>
                                            </>
                                        )}
                                    </dl>
                                    {!!row.dependencies.length && (
                                        <>
                                            <h4>Transaksi sebelumnya</h4>
                                            <ul>
                                                {row.dependencies.map(
                                                    (parent) => (
                                                        <li key={parent.uuid}>
                                                            <code>
                                                                {parent.uuid}
                                                            </code>
                                                            <span>
                                                                {parent.state}
                                                            </span>
                                                        </li>
                                                    ),
                                                )}
                                            </ul>
                                        </>
                                    )}
                                    <p class="footnote">
                                        Tindakan pemulihan resmi menunggu
                                        backend. Diagnosis tidak memberi izin
                                        paksa kirim, hapus atau approval.
                                    </p>
                                </details>
                            </div>
                        </article>
                    ))}
                </div>
            )}
        </section>
    );
}
