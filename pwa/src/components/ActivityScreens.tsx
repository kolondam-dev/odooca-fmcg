import { useEffect, useState } from "preact/hooks";
import type { ComponentChildren } from "preact";
import { diagnoseSync, type SyncDiagnostic } from "../domain/sync-diagnostics";
import { orderHasDiscountRequest } from "../domain/order-pricing";
import { money } from "../domain/format";
import type { FieldStore, QueueItem } from "../storage/store";
import {
    BottomSheet,
    Button,
    Callout,
    Card,
    Chip,
    ListRow,
    Screen,
    ScreenHeader,
    Segmented,
    type Tone,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import type { IconName } from "./Icon";

const hhmm = (iso?: string) =>
    iso
        ? new Date(iso).toLocaleTimeString("id-ID", {
              timeZone: "Asia/Makassar",
              hour: "2-digit",
              minute: "2-digit",
          })
        : "";
const when = (iso?: string) => {
    if (!iso) return "";
    const day = (d: Date) =>
        d.toLocaleDateString("sv-SE", { timeZone: "Asia/Makassar" });
    const d = new Date(iso);
    return day(d) === day(new Date())
        ? hhmm(iso).replace(":", ".")
        : "kemarin atau lebih lama";
};

export function iconFor(type: string): IconName {
    if (type.startsWith("sales.order")) return "bag";
    if (type.includes("check_in") || type.includes("check_out")) return "pin";
    if (type.startsWith("collection")) return "wallet";
    if (type.startsWith("delivery")) return "truck";
    if (type.startsWith("field_expense")) return "receipt";
    if (type.startsWith("hris")) return "user";
    return "clock";
}

/** Ringkas satu transaksi antrean: "Rp 5.300.385 · 09.31" bila ada total. */
function totalOf(item?: QueueItem) {
    const p = item?.command?.payload as { observed_total?: string } | undefined;
    return p?.observed_total ? money(Number(p.observed_total)) : "";
}

export function useDiagnostics(
    store: FieldStore,
    owner: string,
    queue: QueueItem[],
    online: boolean,
) {
    const [rows, setRows] = useState<SyncDiagnostic[]>();
    const [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        void store
            .visitSyncState(owner)
            .then((s) => active && setRows(diagnoseSync(s, owner, online)))
            .catch(
                () =>
                    active &&
                    setError(
                        "Diagnosis tidak tersedia. Data lokal tidak dihapus.",
                    ),
            );
        return () => {
            active = false;
        };
    }, [store, owner, queue, online]);
    return { rows, error };
}

type Status = { tone: Tone; label: string };
function statusOf(r: SyncDiagnostic): Status {
    if (r.group === "review" || r.state === "rejected")
        return {
            tone: "bad",
            label: r.state === "rejected" ? "Ditolak" : "Gagal",
        };
    if (r.group === "approval")
        return { tone: "warn", label: "Menunggu approval" };
    if (r.state === "accepted") return { tone: "ok", label: "Diposting" };
    if (r.state === "sending") return { tone: "info", label: "Terkirim" };
    return { tone: "warn", label: "Menunggu" };
}

function DetailSheet({
    row,
    onClose,
}: {
    row: SyncDiagnostic;
    onClose: () => void;
}) {
    return (
        <BottomSheet title={row.label} onClose={onClose}>
            <Chip tone={statusOf(row).tone}>{row.stateLabel}</Chip>
            <p>{row.message}</p>
            <p class="ui-row__sub">{row.guidance}</p>
            <dl class="pos-dl">
                <dt>UUID transaksi</dt>
                <dd>{row.uuid}</dd>
                <dt>Jenis transaksi</dt>
                <dd>{row.type}</dd>
                <dt>Percobaan kirim</dt>
                <dd>{row.attempts}</dd>
                {row.reference ? (
                    <>
                        <dt>Referensi receipt</dt>
                        <dd>{row.reference}</dd>
                    </>
                ) : null}
                {row.context ? (
                    <>
                        <dt>Sesi kerja</dt>
                        <dd>{row.context.session}</dd>
                        <dt>Tanggal bisnis</dt>
                        <dd>{row.context.date}</dd>
                        <dt>Outlet</dt>
                        <dd>{row.context.outlet}</dd>
                    </>
                ) : null}
            </dl>
            {row.dependencies.length ? (
                <>
                    <p class="ui-sectionlabel">Transaksi sebelumnya</p>
                    <ul>
                        {row.dependencies.map((d) => (
                            <li key={d.uuid}>
                                <code>{d.uuid}</code> {d.state}
                            </li>
                        ))}
                    </ul>
                </>
            ) : null}
            <Button variant="sec" onClick={onClose}>
                Tutup
            </Button>
        </BottomSheet>
    );
}

function Rows({
    rows,
    queue,
    onOpen,
    extra,
}: {
    rows: SyncDiagnostic[];
    queue: QueueItem[];
    onOpen: (r: SyncDiagnostic) => void;
    extra?: (r: SyncDiagnostic) => ComponentChildren;
}) {
    return (
        <Card>
            {rows.map((r, i) => {
                const item = queue.find(
                    (q) => q?.command?.client_uuid === r.uuid,
                );
                const total = totalOf(item);
                return (
                    <div key={r.key}>
                        <ListRow
                            icon={iconFor(r.type)}
                            title={r.label}
                            sub={[total, when(r.occurredAt)]
                                .filter(Boolean)
                                .join(" · ")}
                            status={statusOf(r)}
                            onClick={() => onOpen(r)}
                            divider={i > 0}
                        />
                        {extra?.(r)}
                    </div>
                );
            })}
        </Card>
    );
}

/** Antrean_sinkronisasi: item yang belum diposting server. */
export function QueueScreen({
    store,
    owner,
    queue,
    online,
    syncing,
    onSync,
    onClose,
}: {
    store: FieldStore;
    owner: string;
    queue: QueueItem[];
    online: boolean;
    syncing: boolean;
    onSync: () => void;
    onClose: () => void;
}) {
    useBackLayer(true, onClose);
    const { rows, error } = useDiagnostics(store, owner, queue, online);
    const [open, setOpen] = useState<SyncDiagnostic>();
    const pending = (rows ?? []).filter((r) => r.state !== "accepted");
    return (
        <Screen
            label="Antrean sinkronisasi"
            class="ui-screen--over"
            header={
                <ScreenHeader title="Antrean sinkronisasi" onBack={onClose} />
            }
            footer={
                <Button
                    icon="sync"
                    disabled={!online || syncing}
                    onClick={onSync}
                >
                    {syncing ? "Mengirim…" : "Kirim sekarang"}
                </Button>
            }
        >
            {!online ? (
                <Callout tone="warn" icon="warning">
                    Offline. Item dikirim otomatis saat sinyal kembali.
                </Callout>
            ) : null}
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
            {rows && !pending.length ? (
                <p class="empty">
                    Antrean kosong. Semua aktivitas sudah terkirim.
                </p>
            ) : null}
            {pending.length ? (
                <Rows
                    rows={pending}
                    queue={queue}
                    onOpen={setOpen}
                    extra={(r) =>
                        statusOf(r).label === "Gagal" ? (
                            <div class="pos-retry">
                                <Button
                                    variant="sec"
                                    icon="sync"
                                    disabled={!online || syncing}
                                    onClick={onSync}
                                >
                                    Coba lagi
                                </Button>
                            </div>
                        ) : null
                    }
                />
            ) : null}
            {open ? (
                <DetailSheet row={open} onClose={() => setOpen(undefined)} />
            ) : null}
        </Screen>
    );
}

type ActFilter = "all" | "sent" | "rejected" | "posted";
/** Riwayat_aktivitas: seluruh transaksi perangkat ini. */
export function ActivityScreen({
    store,
    owner,
    queue,
    online,
    onClose,
}: {
    store: FieldStore;
    owner: string;
    queue: QueueItem[];
    online: boolean;
    onClose: () => void;
}) {
    useBackLayer(true, onClose);
    const { rows, error } = useDiagnostics(store, owner, queue, online);
    const [filter, setFilter] = useState<ActFilter>("all");
    const [open, setOpen] = useState<SyncDiagnostic>();
    const pick = (r: SyncDiagnostic) => {
        const label = statusOf(r).label;
        return (
            filter === "all" ||
            (filter === "sent" && label === "Terkirim") ||
            (filter === "rejected" &&
                (label === "Ditolak" || label === "Gagal")) ||
            (filter === "posted" && label === "Diposting")
        );
    };
    const visible = (rows ?? []).filter(pick);
    return (
        <Screen
            label="Riwayat aktivitas"
            class="ui-screen--over"
            header={<ScreenHeader title="Riwayat aktivitas" onBack={onClose} />}
        >
            <Segmented<ActFilter>
                label="Filter aktivitas"
                value={filter}
                onChange={setFilter}
                items={[
                    { value: "all", label: "Semua" },
                    { value: "sent", label: "Terkirim" },
                    { value: "rejected", label: "Ditolak" },
                    { value: "posted", label: "Diposting" },
                ]}
            />
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
            {rows && !visible.length ? (
                <p class="empty">Belum ada aktivitas pada filter ini.</p>
            ) : null}
            {visible.length ? (
                <Rows rows={visible} queue={queue} onOpen={setOpen} />
            ) : null}
            {open ? (
                <DetailSheet row={open} onClose={() => setOpen(undefined)} />
            ) : null}
        </Screen>
    );
}

type ReqFilter = "all" | "wait" | "done";
type Req = {
    key: string;
    title: string;
    sub: string;
    status: Status;
    reason?: string;
};

/** Pengajuan diskon/approval yang berasal dari order di antrean. */
export function requestsFrom(queue: QueueItem[]): Req[] {
    const out: Req[] = [];
    for (const q of queue) {
        // Baris antrean bisa rusak (integritas); jangan sampai merobohkan layar.
        const c = q?.command;
        if (
            !c ||
            (c.type !== "sales.order.submit" && c.type !== "sales.order.revise")
        )
            continue;
        if (!c.payload || typeof c.payload !== "object") continue;
        const p = c.payload as {
            observed_total: string;
            footer_discounts?: { kind: string; amount: number }[];
            lines?: {
                product_id: string;
                discounts?: { kind: string; percent: number }[];
            }[];
        };
        const tactical = orderHasDiscountRequest(p);
        const needs =
            q.state === "needs_approval" ||
            q.receipt?.status === "needs_approval";
        if (!tactical && !needs) continue;
        const status: Status =
            q.state === "rejected"
                ? { tone: "bad", label: "Ditolak" }
                : q.state === "accepted"
                  ? { tone: "ok", label: "Disetujui" }
                  : { tone: "warn", label: "Menunggu" };
        const reason =
            q.state === "rejected"
                ? (q.receipt?.message ?? q.error)
                : undefined;
        const base = `${q.label} · ${money(Number(p.observed_total))}`;
        for (const [i, f] of (p.footer_discounts ?? []).entries())
            if (f.kind === "tactical")
                out.push({
                    key: `${q.key}:f${i}`,
                    title: "Tactical discount footer",
                    sub: `${q.label} · ${money(f.amount)}`,
                    status,
                    reason,
                });
        for (const l of p.lines ?? [])
            for (const [i, d] of (l.discounts ?? []).entries())
                if (d.kind === "tactical")
                    out.push({
                        key: `${q.key}:${l.product_id}:${i}`,
                        title: `Tactical discount baris ${d.percent}%`,
                        sub: `${l.product_id} · ${q.label}`,
                        status,
                        reason,
                    });
        if (needs && !tactical)
            out.push({
                key: q.key,
                title: "Limit kredit terlampaui",
                sub: base,
                status,
                reason,
            });
    }
    return out;
}

/** Riwayat_pengajuan: diskon & approval. `children` memuat alur koreksi SO. */
export function RequestsScreen({
    queue,
    onClose,
    children,
}: {
    queue: QueueItem[];
    onClose: () => void;
    children?: ComponentChildren;
}) {
    useBackLayer(true, onClose);
    const [tab, setTab] = useState<ReqFilter>("all");
    const all = requestsFrom(queue);
    const list = all.filter(
        (r) =>
            tab === "all" ||
            (tab === "wait"
                ? r.status.label === "Menunggu"
                : r.status.label !== "Menunggu"),
    );
    return (
        <Screen
            label="Riwayat pengajuan"
            class="ui-screen--over"
            header={<ScreenHeader title="Riwayat pengajuan" onBack={onClose} />}
        >
            <Segmented<ReqFilter>
                label="Filter pengajuan"
                value={tab}
                onChange={setTab}
                items={[
                    { value: "all", label: "Semua" },
                    { value: "wait", label: "Menunggu" },
                    { value: "done", label: "Selesai" },
                ]}
            />
            {!list.length ? <p class="empty">Belum ada pengajuan.</p> : null}
            {list.map((r) => (
                <Card key={r.key}>
                    <div class="pos-line">
                        <div>
                            <strong>{r.title}</strong>
                            <span class="ui-row__sub">{r.sub}</span>
                        </div>
                        <Chip tone={r.status.tone}>{r.status.label}</Chip>
                    </div>
                    {r.reason ? (
                        <p class="pos-neg">Alasan: {r.reason}</p>
                    ) : null}
                </Card>
            ))}
            {children}
        </Screen>
    );
}
