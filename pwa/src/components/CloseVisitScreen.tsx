import { useMemo, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import type { QueueItem } from "../storage/store";
import { visitOrders } from "../domain/visit-validation";
import {
    Button,
    Callout,
    Card,
    ListRow,
    Screen,
    ScreenHeader,
    Segmented,
    Textarea,
    Tracker,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import type { ComponentChildren } from "preact";

const rupiah = (n: number) =>
    new Intl.NumberFormat("id-ID", {
        style: "currency",
        currency: "IDR",
        maximumFractionDigits: 0,
    }).format(n);

/** Revisi terbaru dari rantai root → revise (supersedes_uuid); root tanpa revisi dikembalikan apa adanya. */
function latestInChain(queue: QueueItem[], root: QueueItem) {
    const revisions = queue.filter(
        (q) =>
            q?.command?.type === "sales.order.revise" &&
            q.command.payload.root_uuid === root.command.client_uuid,
    );
    let tail = root;
    const seen = new Set([root.command.client_uuid]);
    for (;;) {
        const next = revisions.find(
            (q) =>
                q.command.type === "sales.order.revise" &&
                q.command.payload.supersedes_uuid === tail.command.client_uuid,
        );
        if (!next || seen.has(next.command.client_uuid)) return tail;
        seen.add(next.command.client_uuid);
        tail = next;
    }
}

/** Ringkasan order kunjungan aktif dari antrean lokal (hanya baca). Memakai revisi terbaru tiap root; order kunjungan lain tidak dihitung. */
export function orderSummary(queue: QueueItem[], visitId?: string) {
    const rows = visitId
        ? visitOrders(
              queue.filter((q) => q?.command?.type === "sales.order.submit"),
              visitId,
          ).map((root) => latestInChain(queue, root))
        : [];
    let total = 0;
    const skus = new Set<string>();
    for (const q of rows) {
        const p = q.command.payload as {
            observed_total?: string;
            lines?: { product_id: string }[];
        };
        total += Number(p.observed_total ?? 0) || 0;
        for (const l of p.lines ?? []) skus.add(l.product_id);
    }
    const rejected = rows.some(
        (q) => q.state === "rejected" || q.receipt?.status === "rejected",
    );
    const approval = rows.some(
        (q) =>
            q.state === "needs_approval" ||
            q.receipt?.status === "needs_approval",
    );
    return {
        count: rows.length,
        total,
        skuCount: skus.size,
        status: rejected
            ? ({ tone: "bad", label: "Ditolak" } as const)
            : approval
              ? ({ tone: "warn", label: "Menunggu approval" } as const)
              : rows.length && rows.every((q) => q.state === "accepted")
                ? ({ tone: "ok", label: "Diposting" } as const)
                : rows.length
                  ? ({ tone: "info", label: "Tersimpan" } as const)
                  : undefined,
    };
}

/** Layar penuh Selesai kunjungan (DS: Selesai_kunjungan). */
export function CloseVisitScreen({
    outlet,
    queue,
    orders,
    visitId,
    displayDone,
    notes,
    setNotes,
    photoField,
    photoNote,
    busy,
    canSubmit,
    error,
    onOrder,
    onSubmit,
    close,
}: {
    outlet: Snapshot["outlets"][number];
    queue: QueueItem[];
    orders: number;
    /** UUID kunjungan aktif: ringkasan order hanya untuk kunjungan ini. */
    visitId?: string;
    displayDone: boolean;
    notes: string;
    setNotes: (v: string) => void;
    /** Paket foto penutup (bukti wajib, tetap memakai VisitPhotoField). */
    photoField: ComponentChildren;
    photoNote?: string;
    busy: boolean;
    canSubmit: boolean;
    error: string;
    onOrder: () => void;
    onSubmit: () => void;
    close: () => void;
}) {
    useBackLayer(true, close);
    const hasOrder = orders > 0;
    const mode: "order" | "none" = hasOrder ? "order" : "none";
    const [hint, setHint] = useState("");
    const sum = useMemo(() => orderSummary(queue, visitId), [queue, visitId]);
    const ar = outlet.commercial?.ar_outstanding;
    const noteShort = !hasOrder && notes.trim().length < 5;
    return (
        <Screen
            label="Selesai kunjungan"
            class="ui-screen--over"
            header={<ScreenHeader title="Selesai kunjungan" onBack={close} />}
            sub={
                <Tracker
                    label="Tahap kunjungan"
                    steps={[
                        { label: "Check-in", state: "done" },
                        { label: "Tagihan", state: "done" },
                        { label: "Order", state: "done" },
                        { label: "Selesai", state: "cur" },
                    ]}
                />
            }
            footer={
                <Button
                    icon="check"
                    disabled={busy || !canSubmit || noteShort}
                    onClick={onSubmit}
                >
                    {busy ? "Menyimpan…" : "Selesai kunjungan"}
                </Button>
            }
        >
            <Segmented
                label="Hasil kunjungan"
                value={mode}
                onChange={(v) => {
                    setHint(
                        v === mode
                            ? ""
                            : hasOrder
                              ? "Sudah ada order; kunjungan tidak bisa ditutup tanpa order."
                              : "Belum ada order. Buat order dulu untuk memilih Ada order.",
                    );
                    if (v === "order" && !hasOrder) onOrder();
                }}
                items={[
                    { value: "order", label: "Ada order" },
                    { value: "none", label: "Tanpa order" },
                ]}
            />
            {hint ? (
                <p class="ui-row__sub" role="status">
                    {hint}
                </p>
            ) : null}
            <Card>
                <ListRow
                    icon="wallet"
                    title="Tagihan"
                    sub={
                        typeof ar !== "number"
                            ? "Data piutang belum tersedia"
                            : ar > 0
                              ? `Sisa ${rupiah(ar)}`
                              : "Tidak ada piutang berjalan"
                    }
                    status={
                        typeof ar !== "number"
                            ? { tone: "neu", label: "Tidak tersedia" }
                            : ar > 0
                              ? { tone: "warn", label: "Ada sisa" }
                              : { tone: "ok", label: "Lunas" }
                    }
                />
                <ListRow
                    divider
                    icon="cart"
                    title="Order"
                    sub={
                        sum.count
                            ? `${sum.skuCount} SKU · ${rupiah(sum.total)}`
                            : "Belum ada order"
                    }
                    status={sum.status}
                />
                <ListRow
                    divider
                    icon="image"
                    title="Display & stok"
                    status={
                        displayDone
                            ? { tone: "ok", label: "Foto" }
                            : { tone: "neu", label: "Belum" }
                    }
                />
            </Card>
            {hasOrder ? (
                <Button
                    variant="sec"
                    size="md"
                    icon="bag"
                    disabled={busy}
                    onClick={onOrder}
                >
                    + Tambah order lagi untuk outlet ini
                </Button>
            ) : null}
            <Textarea
                label={
                    hasOrder
                        ? "Catatan (opsional)"
                        : "Catatan (wajib min. 5 karakter bila tanpa order)"
                }
                value={notes}
                onInput={setNotes}
                maxLength={500}
                required={!hasOrder}
                minLength={hasOrder ? 0 : 5}
            />
            {photoField}
            {photoNote ? <Callout tone="warn">{photoNote}</Callout> : null}
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
        </Screen>
    );
}
