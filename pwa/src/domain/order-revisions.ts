import { CommandSchema, validateOrder } from "./contracts";
import {
    OrderRevisionSchema,
    revisionKey,
    type OrderRevision,
} from "./order-revision-contracts";
import { VisitLedgerSchema, VisitOrderSchema } from "./visit-contracts";
import {
    MorningRecordSchema,
    morningReady,
    fieldBusinessDate,
} from "./morning";
import { validateOrderQuote } from "./order-pricing";
import { businessRejected } from "./outbox-state";
import { validateVisitSync } from "./visit-validation";
import { validateVisitMedia } from "./visit-evidence";
import { EvidenceIntegrityError } from "./evidence-package";
import type { FieldStore, QueueItem } from "../storage/store";
export function revisionChain(
    rows: QueueItem[],
    owner: string,
    rootId: string,
) {
    const root = rows.find(
        (r) =>
            r.command.client_uuid === rootId &&
            r.command.type === "sales.order.submit",
    );
    if (!root || root.owner !== owner || root.key !== `${owner}:${rootId}`)
        throw new Error("Order sumber hilang/owner berbeda.");
    const source = VisitOrderSchema.parse(root.command.payload);
    const children = rows.filter(
        (r) =>
            r.command.type === "sales.order.revise" &&
            r.command.payload.root_uuid === rootId,
    );
    const chain = [root];
    let parent = root;
    while (true) {
        const next = children.filter(
            (r) =>
                r.command.type === "sales.order.revise" &&
                r.command.payload.supersedes_uuid ===
                    parent.command.client_uuid,
        );
        if (next.length > 1) throw new Error("Revisi ganda tidak diizinkan.");
        if (!next.length) break;
        const child = next[0],
            c = CommandSchema.parse(child.command);
        if (
            c.type !== "sales.order.revise" ||
            child.owner !== owner ||
            child.key !== `${owner}:${c.client_uuid}` ||
            chain.some((r) => r.key === child.key) ||
            !businessRejected(parent) ||
            Date.parse(c.occurred_at) < Date.parse(parent.command.occurred_at)
        )
            throw new Error("Parent/receipt/waktu revisi tidak valid.");
        const p = c.payload,
            daily = MorningRecordSchema.parse(p.daily_source);
        if (
            p.outlet_id !== source.outlet_id ||
            !morningReady(daily, owner, p.business_date) ||
            fieldBusinessDate(new Date(c.occurred_at)) !== p.business_date ||
            daily.snapshot!.version !== p.snapshot_version ||
            !daily.snapshot!.outlets.some((o) => o.id === p.outlet_id)
        )
            throw new Error("Sumber harian/outlet revisi tidak cocok.");
        const invalid = validateOrder(
            p.lines.map((l) => ({
                productId: l.product_id,
                quantity: Number(l.qty),
            })),
            daily.snapshot!,
        );
        if (invalid) throw new Error(invalid);
        validateOrderQuote(p, daily.snapshot!);
        // Preserve principal even when SKU, quantities, UoM or discount change.
        chain.push(child);
        parent = child;
    }
    if (chain.length !== children.length + 1)
        throw new Error("Lineage revisi hilang/cycle.");
    return chain;
}
function assertPrincipals(chain: QueueItem[], ledger: unknown) {
    const rootBody = VisitOrderSchema.parse(chain[0].command.payload);
    const source = VisitLedgerSchema.parse(ledger).visits.find(
        (v) => v.context.visit_uuid === rootBody.visit_context.visit_uuid,
    );
    const original = MorningRecordSchema.parse(source?.morning_source);
    const principal = original.snapshot!.products.find(
        (t) => t.id === rootBody.lines[0].product_id,
    )?.principal;
    for (const row of chain.slice(1)) {
        const p = OrderRevisionSchema.parse(row.command.payload),
            daily = MorningRecordSchema.parse(p.daily_source);
        if (
            !principal ||
            p.lines.some(
                (l) =>
                    daily.snapshot!.products.find((t) => t.id === l.product_id)
                        ?.principal !== principal,
            )
        )
            throw new Error("Principal revisi harus sama dengan order awal.");
    }
}
export function validateRevisionCommit(
    item: QueueItem,
    rows: QueueItem[],
    key: string,
    value: unknown,
    previous: unknown,
    parent: QueueItem | undefined,
    morning: unknown,
    ledger: unknown,
) {
    if (item.command.type !== "sales.order.revise") return;
    const p = item.command.payload;
    if (
        key !== revisionKey(p.root_uuid) ||
        JSON.stringify(CommandSchema.parse(value)) !==
            JSON.stringify(item.command) ||
        !parent ||
        parent.owner !== item.owner ||
        p.supersedes_uuid !== parent.command.client_uuid ||
        JSON.stringify(rows.find((r) => r.key === parent.key)) !==
            JSON.stringify(parent) ||
        !businessRejected(parent) ||
        JSON.stringify(morning) !== JSON.stringify(p.daily_source) ||
        !morningReady(MorningRecordSchema.parse(morning), item.owner)
    )
        throw new Error("Sumber/receipt/snapshot revisi berubah.");
    const before = revisionChain(rows, item.owner, p.root_uuid),
        leaf = before.at(-1)!;
    if (
        leaf.key !== parent.key ||
        (before.length === 1
            ? previous !== undefined
            : JSON.stringify(CommandSchema.parse(previous)) !==
              JSON.stringify(parent.command))
    )
        throw new Error("Revisi bukan ujung lineage.");
    const root = before[0];
    validateVisitSync(root, item.owner, ledger, rows, morning);
    assertPrincipals([...before, item], ledger);

    revisionChain([...rows, item], item.owner, p.root_uuid);
}
export async function validateRevisionMedia(
    item: QueueItem,
    owner: string,
    store: FieldStore,
) {
    if (item.command.type !== "sales.order.revise") return;
    try {
        const state = await store.visitSyncState(owner),
            chain = revisionChain(
                state.rows,
                owner,
                item.command.payload.root_uuid,
            );
        if (
            !chain.some(
                (r) =>
                    r.key === item.key &&
                    JSON.stringify(r.command) === JSON.stringify(item.command),
            )
        )
            throw new Error("Antrean revisi berubah.");
        assertPrincipals(chain, state.ledger);
        validateVisitSync(
            chain[0],
            owner,
            state.ledger,
            state.rows,
            state.morning,
        );
        const leaf = chain.at(-1)!;
        if (
            JSON.stringify(
                await store.draft(
                    owner,
                    revisionKey(item.command.payload.root_uuid),
                ),
            ) !== JSON.stringify(leaf.command)
        )
            throw new Error("Pointer revisi berubah.");
        await validateVisitMedia(
            state.rows,
            owner,
            store,
            VisitOrderSchema.parse(chain[0].command.payload).visit_context
                .visit_uuid,
        );
        const after = await store.visitSyncState(owner);
        if (
            JSON.stringify(state) !== JSON.stringify(after) ||
            JSON.stringify(
                await store.draft(
                    owner,
                    revisionKey(item.command.payload.root_uuid),
                ),
            ) !== JSON.stringify(leaf.command)
        )
            throw new Error("Sumber revisi berubah saat membaca media.");
    } catch {
        throw new EvidenceIntegrityError(
            "Order/revisi/sumber/bukti perlu review; data tetap tersimpan.",
        );
    }
}
export async function submitRevision(
    store: FieldStore,
    owner: string,
    parent: QueueItem,
    p: OrderRevision,
    outbox: import("./outbox").Outbox,
) {
    const rows = await store.list(owner),
        chain = revisionChain(rows, owner, p.root_uuid);
    if (chain.at(-1)?.key !== parent.key)
        throw new Error("Parent revisi berubah.");
    if (parent.command.type === "sales.order.revise")
        await validateRevisionMedia(parent, owner, store);
    else {
        const state = await store.visitSyncState(owner);
        validateVisitSync(
            parent,
            owner,
            state.ledger,
            state.rows,
            state.morning,
        );
        await validateVisitMedia(
            state.rows,
            owner,
            store,
            VisitOrderSchema.parse(parent.command.payload).visit_context
                .visit_uuid,
        );
    }
    const uuid = crypto.randomUUID(),
        at = new Date().toISOString();
    return outbox.enqueue(
        "sales.order.revise",
        OrderRevisionSchema.parse(p),
        `Revisi SO • ${p.outlet_id}`,
        uuid,
        {
            key: revisionKey(p.root_uuid),
            expected: chain.length === 1 ? undefined : parent.command,
            value: {
                schema_version: 1,
                client_uuid: uuid,
                occurred_at: at,
                type: "sales.order.revise",
                payload: p,
            },
            guards: { source: parent },
            occurredAt: at,
        },
    );
}
