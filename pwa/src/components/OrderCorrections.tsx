import { useEffect, useState } from "preact/hooks";
import { businessRejected } from "../domain/outbox-state";
import { revisionChain, submitRevision } from "../domain/order-revisions";
import {
    OrderRevisionSchema,
    type OrderRevision,
} from "../domain/order-revision-contracts";
import { VisitOrderSchema } from "../domain/visit-contracts";
import { orderQuote, type OrderUom } from "../domain/order-pricing";
import { morningReady, type MorningRecord } from "../domain/morning";
import type { FieldStore, QueueItem } from "../storage/store";
import type { Outbox } from "../domain/outbox";
import { money } from "../domain/format";
function orderBody(row: QueueItem) {
    return row.command.type === "sales.order.revise"
        ? OrderRevisionSchema.parse(row.command.payload)
        : VisitOrderSchema.parse(row.command.payload);
}
export function OrderCorrections({
    store,
    owner,
    morning,
    queue,
    engine,
    changed,
}: {
    store: FieldStore;
    owner: string;
    morning?: MorningRecord;
    queue: QueueItem[];
    engine: Outbox;
    changed: () => void;
}) {
    const roots = queue.filter(
        (r) =>
            r.command?.type === "sales.order.submit" &&
            r.command.payload?.visit_context,
    );
    const [parent, setParent] = useState<QueueItem>();
    const [root, setRoot] = useState("");
    const [qty, setQty] = useState<Record<string, number>>({}),
        [units, setUnits] = useState<Record<string, OrderUom>>({});
    const [percent, setPercent] = useState(0),
        [discountReason, setDiscountReason] = useState(""),
        [note, setNote] = useState(""),
        [reason, setReason] = useState("");
    const [loaded, setLoaded] = useState(false),
        [busy, setBusy] = useState(false),
        [message, setMessage] = useState("");
    const snapshot = morning?.snapshot;
    const key =
        parent && morning
            ? `sales-revision-form:${parent.command.client_uuid}:v1`
            : undefined;
    let preview: ReturnType<typeof orderQuote> | undefined;
    try {
        if (snapshot)
            preview = orderQuote(
                Object.entries(qty)
                    .filter(([, q]) => q > 0)
                    .map(([product_id, q]) => ({
                        product_id,
                        qty: String(q),
                        uom: units[product_id] ?? "carton",
                    })),
                snapshot,
                percent > 0 ? { percent, reason: discountReason } : undefined,
            );
    } catch {
        /* Incomplete input is kept in the editor. */
    }
    useEffect(() => {
        let active = true;
        setLoaded(false);
        if (!parent || !key) return;
        void (async () => {
            const saved = await store.draft(owner, key);
            const body = saved
                ? OrderRevisionSchema.parse(saved)
                : parent.command.type === "sales.order.revise"
                  ? OrderRevisionSchema.parse(parent.command.payload)
                  : VisitOrderSchema.parse(parent.command.payload);
            if (
                saved &&
                (body as OrderRevision).supersedes_uuid !==
                    parent.command.client_uuid
            )
                throw new Error("Draft koreksi berbeda parent.");
            if (active) {
                setQty(
                    Object.fromEntries(
                        body.lines.map((l) => [l.product_id, Number(l.qty)]),
                    ),
                );
                setUnits(
                    Object.fromEntries(
                        body.lines.map((l) => [l.product_id, l.uom]),
                    ),
                );
                setPercent(body.discount_request?.percent ?? 0);
                setDiscountReason(body.discount_request?.reason ?? "");
                setNote(body.note);
                setReason(
                    saved ? (body as OrderRevision).correction_reason : "",
                );
                setLoaded(true);
            }
        })().catch((e) => {
            if (active) setMessage(e.message);
        });
        return () => {
            active = false;
        };
    }, [owner, key, morning?.sessionId]);
    function open(leaf: QueueItem, rootId: string) {
        setMessage("");
        if (!morningReady(morning, owner)) {
            setMessage("Daily sync hari ini wajib sebelum koreksi.");
            return;
        }
        setRoot(rootId);
        setParent(leaf);
    }
    async function save(send: boolean) {
        if (!parent || !morning || !snapshot || !key || busy) return;
        setBusy(true);
        setMessage("");
        try {
            const lines = Object.entries(qty)
                .filter(([, q]) => q > 0)
                .map(([product_id, q]) => ({
                    product_id,
                    qty: String(q),
                    uom: units[product_id] ?? ("carton" as OrderUom),
                }));
            const request =
                percent > 0 ? { percent, reason: discountReason } : undefined;
            const p = OrderRevisionSchema.parse({
                revision_version: 1,
                root_uuid: root,
                supersedes_uuid: parent.command.client_uuid,
                correction_reason: reason,
                outlet_id: orderBody(parent).outlet_id,
                snapshot_version: snapshot.version,
                business_date: morning.businessDate,
                daily_source: morning,
                lines,
                note,
                pricing_version: 1,
                ...(request ? { discount_request: request } : {}),
                observed_total: String(
                    orderQuote(lines, snapshot, request).requestedTotal,
                ),
            });
            if (send) {
                await submitRevision(store, owner, parent, p, engine);
                setParent(undefined);
                changed();
                void engine.flush();
                setMessage(
                    "Revisi baru masuk antrean; pengajuan dan keputusan sebelumnya tetap utuh.",
                );
            } else {
                await store.draft(owner, key, p);
                setMessage("Draft koreksi SO tersimpan offline.");
            }
        } catch (e) {
            setMessage(
                e instanceof Error ? e.message : "Gagal menyimpan koreksi.",
            );
        } finally {
            setBusy(false);
        }
    }
    if (!roots.length) return null;
    return (
        <section class="paper-card">
            <h3>Koreksi Sales Order</h3>
            <p>
                Koreksi administratif dari pengajuan ditolak, termasuk setelah
                sesi toko ditutup. Daily sync hari ini wajib; bukan membuka
                ulang kunjungan atau mengubah order diterima.
            </p>
            {roots.map((r) => {
                let chain: QueueItem[];
                try {
                    chain = revisionChain(queue, owner, r.command.client_uuid);
                } catch (e) {
                    return (
                        <p key={r.key}>
                            Riwayat SO perlu review:{" "}
                            {e instanceof Error ? e.message : "invalid"}
                        </p>
                    );
                }
                const leaf = chain.at(-1)!;
                return (
                    <details key={r.key}>
                        <summary>
                            Riwayat SO · {r.label} · {chain.length} pengajuan
                        </summary>
                        {chain.map((h) => (
                            <article key={h.key}>
                                <p>
                                    {h.command.client_uuid.slice(0, 8)} ·{" "}
                                    {h.state}
                                </p>
                                <p>
                                    {h.receipt?.message ??
                                        "Belum ada keputusan"}
                                </p>
                                <p>
                                    {h.command.type === "sales.order.revise"
                                        ? `Alasan koreksi: ${h.command.payload.correction_reason}`
                                        : "Pengajuan awal"}
                                </p>
                                <p>
                                    {(
                                        orderBody(h).lines as {
                                            product_id: string;
                                            qty: string;
                                            uom: string;
                                        }[]
                                    )
                                        .map(
                                            (l) =>
                                                `${l.product_id}: ${l.qty} ${l.uom}`,
                                        )
                                        .join("; ")}
                                </p>
                                <p>
                                    Estimasi{" "}
                                    {money(Number(orderBody(h).observed_total))}
                                </p>
                            </article>
                        ))}
                        {businessRejected(leaf) && (
                            <button
                                class="secondary"
                                onClick={() =>
                                    open(leaf, r.command.client_uuid)
                                }
                            >
                                Koreksi SO ditolak
                            </button>
                        )}
                    </details>
                );
            })}
            {parent && snapshot && (
                <fieldset disabled={busy || !loaded}>
                    <h4>
                        Revisi atas {parent.command.client_uuid.slice(0, 8)}
                    </h4>
                    <p>{parent.receipt?.message}</p>
                    <label>
                        Alasan koreksi SO
                        <textarea
                            value={reason}
                            maxLength={500}
                            onInput={(e) => setReason(e.currentTarget.value)}
                        />
                    </label>
                    {snapshot.products.map((p) => (
                        <div key={p.id}>
                            <strong>
                                {p.name} · {p.principal} · {money(p.price)}
                                /karton
                            </strong>
                            <label>
                                Qty revisi {p.name}
                                <input
                                    type="number"
                                    min="0"
                                    max="999"
                                    value={qty[p.id] ?? 0}
                                    onInput={(e) =>
                                        setQty((v) => ({
                                            ...v,
                                            [p.id]: Number(
                                                e.currentTarget.value,
                                            ),
                                        }))
                                    }
                                />
                            </label>
                            <label>
                                Satuan revisi {p.name}
                                <select
                                    aria-label={`Satuan revisi ${p.name}`}
                                    value={units[p.id] ?? "carton"}
                                    onChange={(e) =>
                                        setUnits((v) => ({
                                            ...v,
                                            [p.id]: e.currentTarget
                                                .value as OrderUom,
                                        }))
                                    }
                                >
                                    <option value="carton">Karton144pcs</option>
                                    <option value="pack">Pack12pcs</option>
                                    <option value="pcs">Pcs</option>
                                </select>
                            </label>
                        </div>
                    ))}
                    <label>
                        Diskon revisi (%)
                        <input
                            type="number"
                            min="0"
                            max="100"
                            value={percent}
                            onInput={(e) =>
                                setPercent(Number(e.currentTarget.value))
                            }
                        />
                    </label>
                    {percent > 0 && (
                        <label>
                            Alasan diskon revisi
                            <textarea
                                value={discountReason}
                                onInput={(e) =>
                                    setDiscountReason(e.currentTarget.value)
                                }
                            />
                        </label>
                    )}
                    <label>
                        Catatan SO revisi
                        <textarea
                            value={note}
                            maxLength={500}
                            onInput={(e) => setNote(e.currentTarget.value)}
                        />
                    </label>
                    {preview && (
                        <p>
                            Gross revisi {money(preview.gross)} · diskon diminta{" "}
                            {money(preview.requestedDiscount)} · estimasi revisi{" "}
                            {money(preview.requestedTotal)}. Harga memakai paket
                            hari ini; menunggu approval baru.
                        </p>
                    )}
                    <button class="secondary" onClick={() => void save(false)}>
                        Simpan draft koreksi SO
                    </button>
                    <button class="primary" onClick={() => void save(true)}>
                        Ajukan revisi SO
                    </button>
                    <button
                        class="secondary"
                        onClick={() => setParent(undefined)}
                    >
                        Tutup editor koreksi
                    </button>
                </fieldset>
            )}
            {message && <p role="status">{message}</p>}
        </section>
    );
}
