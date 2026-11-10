import { useEffect, useState } from "preact/hooks";
import { businessRejected } from "../domain/outbox-state";
import {
    assertRootOrderDay,
    rootOrderDate,
    ORDER_DAY_CLOSED,
    revisionChain,
    submitRevision,
} from "../domain/order-revisions";
import { OrderRevisionSchema } from "../domain/order-revision-contracts";
import { VisitOrderSchema } from "../domain/visit-contracts";
import { type OrderUom } from "../domain/order-pricing";
import {
    cartFromLegacy,
    cartLines,
    cartTotals,
    tierText,
    type Cart,
    type LineDiscounts,
} from "../domain/order-cart";
import type { FooterDiscount } from "../domain/order-discount";
import {
    BottomSheet,
    Button,
    Callout,
    Card,
    Chip,
    Screen,
    ScreenHeader,
    Textarea,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import { DiscountSheet } from "./DiscountSheets";
import { ProductCard } from "./OrderScreen";
import { setTier as setTierFn } from "../domain/order-cart";
import {
    MORNING_KEY,
    MorningRecordSchema,
    morningReady,
    type MorningRecord,
} from "../domain/morning";
import type { FieldStore, QueueItem } from "../storage/store";
import type { Outbox } from "../domain/outbox";
import { useBusinessDate } from "./useBusinessDate";
import type { Snapshot } from "../domain/contracts";
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
    const [message, setMessage] = useState("");
    const today = useBusinessDate();
    const [draftSnapshot, setDraftSnapshot] = useState<Snapshot>();
    const snapshot = morning?.snapshot ?? draftSnapshot;
    const selectedRoot = roots.find((r) => r.command.client_uuid === root);
    let editorClosed = !!parent;
    try {
        if (selectedRoot)
            editorClosed = rootOrderDate(selectedRoot, owner) !== today;
    } catch {
        /* Read-only until source is reviewed. */
    }
    async function open(leaf: QueueItem, rootId: string) {
        setMessage("");
        const source = roots.find((r) => r.command.client_uuid === rootId);
        if (!source) return;
        let currentMorning = morning;
        if (!currentMorning) {
            try {
                const restored = await store.draft(owner, MORNING_KEY);
                if (restored)
                    currentMorning = MorningRecordSchema.parse(restored);
            } catch {
                /* fallback to state */
            }
        }
        if (
            rootOrderDate(source, owner) === today &&
            !morningReady(currentMorning, owner)
        ) {
            setMessage("Daily sync hari ini wajib sebelum koreksi.");
            return;
        }
        if (currentMorning?.snapshot) {
            setDraftSnapshot(currentMorning.snapshot);
        } else {
            setDraftSnapshot(undefined);
        }
        setRoot(rootId);
        setParent(leaf);
    }
    if (!roots.length) return null;
    return (
        <section class="paper-card">
            <h3>Koreksi Sales Order</h3>
            <p>
                Koreksi dan approval wajib selesai pada hari root SO dalam WITA,
                termasuk bila sesi toko sudah ditutup. Salesman wajib
                follow-up/push approval ke manager secara manual. Daily sync
                wajib. Lewat hari, draft/pending tetap tersimpan untuk tindak
                lanjut, tanpa keputusan otomatis.
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
                const leaf = chain.at(-1)!,
                    expired = rootOrderDate(r, owner) !== today;
                return (
                    <details key={r.key}>
                        <summary>
                            Riwayat SO · {r.label} · {chain.length} pengajuan
                        </summary>
                        {expired && <p>{ORDER_DAY_CLOSED}</p>}
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
                                        orderBody(h).lines as (
                                            | {
                                                  product_id: string;
                                                  qty: string;
                                                  uom: string;
                                              }
                                            | {
                                                  product_id: string;
                                                  tiers: {
                                                      uom: string;
                                                      qty: string;
                                                  }[];
                                              }
                                        )[]
                                    )
                                        .map((l) =>
                                            "tiers" in l
                                                ? `${l.product_id}: ${l.tiers.map((t) => `${t.qty} ${t.uom}`).join(" + ")}`
                                                : `${l.product_id}: ${l.qty} ${l.uom}`,
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
                                    void open(leaf, r.command.client_uuid)
                                }
                            >
                                {expired
                                    ? "Lihat draft koreksi lewat hari"
                                    : "Koreksi SO ditolak"}
                            </button>
                        )}
                    </details>
                );
            })}
            {parent && snapshot && selectedRoot ? (
                <KoreksiScreen
                    parent={parent}
                    root={root}
                    rootItem={selectedRoot}
                    snapshot={snapshot}
                    morning={morning}
                    owner={owner}
                    store={store}
                    engine={engine}
                    editorClosed={editorClosed}
                    onClose={() => setParent(undefined)}
                    onSent={(text) => {
                        setParent(undefined);
                        changed();
                        void engine.flush();
                        setMessage(text);
                    }}
                />
            ) : null}
            {message && <p role="status">{message}</p>}
        </section>
    );
}

type FormState = {
    cart: Cart;
    lineDisc: LineDiscounts;
    footerDisc: FooterDiscount[];
    reason: string;
    note: string;
    supersedes: string;
};

/** Bentuk awal formulir dari body induk (v2 apa adanya; v1 dipetakan ke v2). */
function formFromBody(body: ReturnType<typeof orderBody>): FormState {
    const cart: Cart = {};
    const lineDisc: LineDiscounts = {};
    const legacy: { product_id: string; qty: string; uom: OrderUom }[] = [];
    for (const l of body.lines) {
        if ("tiers" in l) {
            cart[l.product_id] = Object.fromEntries(
                l.tiers.map((t) => [t.uom, Number(t.qty)]),
            );
            if (l.discounts?.length) lineDisc[l.product_id] = l.discounts;
        } else legacy.push(l);
    }
    for (const l of legacy)
        Object.assign(
            cart,
            cartFromLegacy(
                { [l.product_id]: Number(l.qty) },
                {
                    [l.product_id]: l.uom,
                },
            ),
        );
    // v1: diskon order (%) dipetakan menjadi pengajuan tactical pada tiap baris.
    if (body.discount_request)
        for (const id of Object.keys(cart))
            lineDisc[id] = [
                {
                    kind: "tactical",
                    percent: body.discount_request.percent,
                    reason: body.discount_request.reason,
                },
            ];
    return {
        cart,
        lineDisc,
        footerDisc: body.footer_discounts ?? [],
        reason: "",
        note: body.note,
        supersedes: "",
    };
}

function KoreksiScreen({
    parent,
    root,
    rootItem,
    snapshot,
    morning,
    owner,
    store,
    engine,
    editorClosed,
    onClose,
    onSent,
}: {
    parent: QueueItem;
    root: string;
    rootItem: QueueItem;
    snapshot: Snapshot;
    morning?: MorningRecord;
    owner: string;
    store: FieldStore;
    engine: Outbox;
    editorClosed: boolean;
    onClose: () => void;
    onSent: (message: string) => void;
}) {
    const key = `sales-revision-form:${parent.command.client_uuid}:v2`;
    const [form, setForm] = useState<FormState>();
    // Lembar diskon menumpuk di atas daftar (bukan menggantinya) agar lapis Back tidak berlomba.
    const [sheet, setSheet] = useState<null | "lines" | "discounts">(null);
    const [lineEdit, setLineEdit] = useState<string | null>(null);
    const [footerEdit, setFooterEdit] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    useBackLayer(true, onClose);
    useEffect(() => {
        let active = true;
        void (async () => {
            const saved = (await store.draft(owner, key)) as
                | FormState
                | undefined;
            const initial =
                saved && saved.supersedes === parent.command.client_uuid
                    ? saved
                    : {
                          ...formFromBody(orderBody(parent)),
                          supersedes: parent.command.client_uuid,
                      };
            if (active) setForm(initial);
        })().catch((e) => active && setError(e.message));
        return () => {
            active = false;
        };
    }, [key]);
    useEffect(() => {
        if (form && !editorClosed)
            void store.draft(owner, key, form).catch(() => {});
    }, [form]);
    if (!form)
        return (
            <Screen
                label="Koreksi order"
                class="ui-screen--over"
                header={<ScreenHeader title="Koreksi order" onBack={onClose} />}
            >
                <p class="empty">Memuat…</p>
            </Screen>
        );
    const totals = cartTotals(
        form.cart,
        form.lineDisc,
        form.footerDisc,
        snapshot,
    );
    const parentBody = orderBody(parent);
    const principal = snapshot.products.find((p) =>
        Object.keys(form.cart).includes(p.id),
    )?.principal;
    const outlet = snapshot.outlets.find((o) => o.id === parentBody.outlet_id);
    const set = (patch: Partial<FormState>) =>
        setForm((cur) => (cur ? { ...cur, ...patch } : cur));
    async function send() {
        if (busy || !form) return;
        setBusy(true);
        setError("");
        try {
            assertRootOrderDay(rootItem, owner);
            if (!morning)
                throw new Error("Daily sync hari ini wajib sebelum koreksi.");
            if (form.reason.trim().length < 3)
                throw new Error("Catatan untuk SPV wajib minimal 3 karakter.");
            if (totals.stale.length)
                throw new Error("Ada SKU yang tidak ada lagi di katalog.");
            if (totals.errors.length) throw new Error(totals.errors[0]);
            const { lines } = cartLines(form.cart, form.lineDisc, snapshot);
            const payload = OrderRevisionSchema.parse({
                revision_version: 1,
                root_uuid: root,
                supersedes_uuid: parent.command.client_uuid,
                correction_reason: form.reason.trim(),
                outlet_id: parentBody.outlet_id,
                snapshot_version: snapshot.version,
                business_date: morning.businessDate,
                daily_source: morning,
                lines,
                note: form.note,
                pricing_version: 2,
                ...(form.footerDisc.length
                    ? { footer_discounts: form.footerDisc }
                    : {}),
                observed_total: String(totals.total),
            });
            await submitRevision(store, owner, parent, payload, engine);
            await store.removeDraft(owner, key);
            onSent(
                "Revisi baru masuk antrean; pengajuan dan keputusan sebelumnya tetap utuh.",
            );
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Gagal mengirim koreksi.",
            );
        } finally {
            setBusy(false);
        }
    }
    const lineProduct = lineEdit
        ? snapshot.products.find((p) => p.id === lineEdit)
        : undefined;
    const programs = snapshot.discount_programs ?? [];
    return (
        <Screen
            label="Koreksi order"
            class="ui-screen--over"
            header={
                <ScreenHeader
                    title="Koreksi order"
                    onBack={onClose}
                    status={{ tone: "bad", label: "Ditolak" }}
                />
            }
            footer={
                <Button
                    icon="arrow"
                    disabled={busy || editorClosed || !totals.skuCount}
                    onClick={() => void send()}
                >
                    {busy ? "Mengirim…" : "Kirim ulang"}
                </Button>
            }
        >
            <Callout tone="bad" alert title="Ditolak oleh SPV">
                {parent.receipt?.message ?? "Belum ada alasan dari SPV."}
            </Callout>
            {editorClosed ? (
                <Callout tone="warn">{ORDER_DAY_CLOSED}</Callout>
            ) : null}
            <p class="ui-sectionlabel">{outlet?.name ?? "Outlet"} · SO draft</p>
            <Card>
                {totals.quote.lines.map((ql) => {
                    const product = snapshot.products.find(
                        (p) => p.id === ql.product_id,
                    )!;
                    return (
                        <div key={ql.product_id}>
                            <div class="pos-line">
                                <div>
                                    <strong>{product.name}</strong>
                                    <span class="ui-row__sub">
                                        {tierText(
                                            product,
                                            form.cart[ql.product_id] ?? {},
                                        )}
                                    </span>
                                </div>
                                <strong>{money(ql.gross)}</strong>
                            </div>
                            {(form.lineDisc[ql.product_id] ?? []).map(
                                (d, i) => (
                                    <div class="pos-line" key={i}>
                                        <div>
                                            <strong>
                                                {d.kind === "tactical"
                                                    ? "Diskon extra"
                                                    : "Diskon program"}
                                            </strong>
                                            <span class="ui-row__sub">
                                                {d.kind === "tactical"
                                                    ? "Tactical discount"
                                                    : d.program_id}{" "}
                                                · {d.percent}%
                                            </span>
                                        </div>
                                        <strong class="pos-neg">
                                            −{money(ql.steps[i]?.amount ?? 0)}
                                        </strong>
                                    </div>
                                ),
                            )}
                        </div>
                    );
                })}
                {totals.quote.footerSteps.map((d, i) => (
                    <div class="pos-line" key={`f${i}`}>
                        <div>
                            <strong>Diskon footer</strong>
                            <span class="ui-row__sub">
                                {form.footerDisc[i]?.kind === "tactical"
                                    ? "Tactical discount"
                                    : form.footerDisc[i] &&
                                        "program_id" in form.footerDisc[i]!
                                      ? (
                                            form.footerDisc[i] as {
                                                program_id: string;
                                            }
                                        ).program_id
                                      : ""}
                            </span>
                        </div>
                        <strong class="pos-neg">−{money(d.amount)}</strong>
                    </div>
                ))}
                <div class="pos-totals__grand">
                    <span>Total</span>
                    <strong>{money(totals.total)}</strong>
                </div>
            </Card>
            <Button
                variant="sec"
                icon="box"
                disabled={editorClosed}
                onClick={() => setSheet("lines")}
            >
                Ubah baris order
            </Button>
            <Button
                variant="sec"
                icon="tag"
                disabled={editorClosed || !totals.skuCount}
                onClick={() => setSheet("discounts")}
            >
                Ubah diskon
            </Button>
            <Textarea
                label="Catatan untuk SPV"
                value={form.reason}
                maxLength={500}
                placeholder="Contoh: diskon dikurangi jadi Rp 15.000"
                disabled={editorClosed}
                onInput={(reason) => set({ reason })}
            />
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
            {sheet === "lines" ? (
                <BottomSheet
                    title="Ubah baris order"
                    onClose={() => setSheet(null)}
                >
                    {snapshot.products
                        .filter((p) => !principal || p.principal === principal)
                        .slice(0, 60)
                        .map((p) => (
                            <ProductCard
                                key={p.id}
                                product={p}
                                catalogVersion={snapshot.catalog_version}
                                tiers={form.cart[p.id] ?? {}}
                                stock={p.stock}
                                discounts={form.lineDisc[p.id] ?? []}
                                onDiscount={() => setLineEdit(p.id)}
                                onInfo={() => {}}
                                onTier={(uom, value) =>
                                    set({
                                        cart: setTierFn(
                                            form.cart,
                                            p.id,
                                            uom,
                                            value,
                                        ),
                                    })
                                }
                            />
                        ))}
                    <Button onClick={() => setSheet(null)}>Selesai</Button>
                </BottomSheet>
            ) : null}
            {sheet === "discounts" ? (
                <BottomSheet title="Ubah diskon" onClose={() => setSheet(null)}>
                    {totals.quote.lines.map((ql) => {
                        const product = snapshot.products.find(
                            (p) => p.id === ql.product_id,
                        )!;
                        return (
                            <Button
                                key={ql.product_id}
                                variant="sec"
                                onClick={() => setLineEdit(ql.product_id)}
                            >
                                Diskon baris · {product.name}
                                {form.lineDisc[ql.product_id]?.length ? (
                                    <Chip tone="warn">
                                        {form.lineDisc[ql.product_id]!.length}
                                    </Chip>
                                ) : null}
                            </Button>
                        );
                    })}
                    <Button variant="sec" onClick={() => setFooterEdit(true)}>
                        Diskon footer
                    </Button>
                    <Button onClick={() => setSheet(null)}>Selesai</Button>
                </BottomSheet>
            ) : null}
            {lineProduct ? (
                <DiscountSheet
                    mode="line"
                    title={`Diskon baris · ${lineProduct.name}`}
                    base={
                        totals.quote.lines.find(
                            (l) => l.product_id === lineProduct.id,
                        )?.gross ?? 0
                    }
                    programs={programs.filter(
                        (p) =>
                            p.scope === "line" &&
                            (!p.principal ||
                                p.principal === lineProduct.principal) &&
                            (!p.product_ids?.length ||
                                p.product_ids.includes(lineProduct.id)),
                    )}
                    usedElsewhere={{}}
                    initial={form.lineDisc[lineProduct.id] ?? []}
                    onClose={() => setLineEdit(null)}
                    onApply={(next) => {
                        const copy = { ...form.lineDisc };
                        if (next.length) copy[lineProduct.id] = next;
                        else delete copy[lineProduct.id];
                        set({ lineDisc: copy });
                        setLineEdit(null);
                    }}
                />
            ) : null}
            {footerEdit ? (
                <DiscountSheet
                    mode="footer"
                    title="Diskon footer order"
                    base={totals.quote.afterLine}
                    programs={programs.filter(
                        (p) =>
                            p.scope === "footer" &&
                            (!p.principal || p.principal === principal),
                    )}
                    usedElsewhere={{}}
                    initial={form.footerDisc}
                    onClose={() => setFooterEdit(false)}
                    onApply={(next) => {
                        set({ footerDisc: next });
                        setFooterEdit(false);
                    }}
                />
            ) : null}
        </Screen>
    );
}
