import {
    CollectionReceiptSchema,
    CollectionTaskSchema,
    collectionKey,
    collectionSourceKey,
    normalizedReference,
    type CollectionTask,
} from "./collection-contracts";
import { businessRejected } from "./outbox-state";
import { CommandSchema } from "./contracts";
import { requireVisitFix } from "./visit-validation";
import {
    assertLocalEvidence,
    EvidenceIntegrityError,
} from "./evidence-package";
import type { FieldStore, QueueItem } from "../storage/store";
export function validateCollection(value: unknown, owner: string, at: string) {
    const p = CollectionReceiptSchema.parse(value),
        s = p.source;
    if (
        s.delivery.owner !== owner ||
        new Date(at).toLocaleDateString("en-CA", {
            timeZone: "Asia/Makassar",
        }) !== s.delivery.business_date ||
        new Date(s.issued_at).toLocaleDateString("en-CA", {
            timeZone: "Asia/Makassar",
        }) !== s.delivery.business_date ||
        Date.parse(s.issued_at) > Date.parse(at) ||
        Date.parse(s.issued_at) > Date.parse(p.evidence.capturedAt)
    )
        throw new Error("Penugasan tagihan/waktu tidak cocok.");
    if (BigInt(p.amount) > BigInt(s.amount_due))
        throw new Error("Nominal melebihi saldo tagihan contoh.");
    requireVisitFix(
        {
            latitude: p.evidence.latitude,
            longitude: p.evidence.longitude,
            accuracy: p.evidence.accuracy,
            sampled_at: p.evidence.capturedAt,
        },
        s.delivery.site,
        Date.parse(at),
    );
    return p;
}
export function assertCollectionSource(value: unknown, source: CollectionTask) {
    if (
        !Array.isArray(value) ||
        !value.some(
            (v) =>
                JSON.stringify(CollectionTaskSchema.parse(v)) ===
                JSON.stringify(source),
        )
    )
        throw new Error("Sumber/capability tagihan berubah atau hilang.");
}
export function collectionLineage(
    rows: QueueItem[],
    owner: string,
    reference: string,
) {
    const parsed = rows
        .filter((r) => r.command.type === "collection.receipt.submit")
        .map((r) => {
            const c = CommandSchema.parse(r.command);
            if (c.type !== "collection.receipt.submit") throw new Error("DTO");
            const p = validateCollection(c.payload, owner, c.occurred_at);
            if (r.owner !== owner || r.key !== `${owner}:${c.client_uuid}`)
                throw new Error("Envelope collection invalid.");
            return { r, c, p };
        });
    const group = parsed.filter(
        (x) =>
            normalizedReference(x.p.source.receivable_reference) ===
            normalizedReference(reference),
    );
    const roots = group.filter((x) => !x.p.supersedes_uuid);
    if (roots.length !== 1)
        throw new Error("Tagihan mempunyai root ganda/hilang.");
    const chain: QueueItem[] = [];
    let node = roots[0];
    while (node) {
        if (chain.some((r) => r.key === node.r.key))
            throw new Error("Cycle collection.");
        chain.push(node.r);
        const children = group.filter(
            (x) => x.p.supersedes_uuid === node.c.client_uuid,
        );
        if (children.length > 1) throw new Error("Koreksi ganda.");
        if (!children.length) break;
        const next = children[0];
        if (
            !businessRejected(node.r) ||
            JSON.stringify(next.p.source) !== JSON.stringify(node.p.source) ||
            Date.parse(next.c.occurred_at) < Date.parse(node.c.occurred_at) ||
            Date.parse(next.p.evidence.capturedAt) <
                Date.parse(node.c.occurred_at)
        )
            throw new Error("Parent/receipt/sumber/waktu koreksi invalid.");
        node = next;
    }
    if (chain.length !== group.length)
        throw new Error("Parent hilang/cycle collection.");
    if (new Set(parsed.map((x) => x.p.evidence.id)).size !== parsed.length)
        throw new Error("Foto sudah dipakai.");
    for (const x of group)
        for (const y of parsed) {
            if (group.includes(y)) continue;
            if (
                normalizedReference(x.p.receipt_number) ===
                    normalizedReference(y.p.receipt_number) ||
                (x.p.transfer_reference &&
                    y.p.transfer_reference &&
                    normalizedReference(x.p.transfer_reference) ===
                        normalizedReference(y.p.transfer_reference))
            )
                throw new Error(
                    "Nomor bukti/ref transfer sudah dipakai. Perlu review.",
                );
        }
    return chain;
}
export function validateCollectionRows(item: QueueItem, rows: QueueItem[]) {
    const c = CommandSchema.parse(item.command);
    if (c.type !== "collection.receipt.submit") throw new Error("DTO");
    const p = validateCollection(c.payload, item.owner, c.occurred_at);
    if (item.key !== `${item.owner}:${c.client_uuid}`)
        throw new Error("Envelope");
    collectionLineage(
        rows.some((r) => r.key === item.key) ? rows : [...rows, item],
        item.owner,
        p.source.receivable_reference,
    );
    return p;
}
export function validateCollectionCommit(
    item: QueueItem,
    key: string,
    value: unknown,
    rows: QueueItem[],
    previous?: unknown,
) {
    const p = validateCollectionRows(item, rows);
    if (
        key !== collectionKey(p.source) ||
        JSON.stringify(CommandSchema.parse(value)) !==
            JSON.stringify(item.command)
    )
        throw new Error("Binding collection invalid.");
    if (p.supersedes_uuid) {
        const parent = rows.find(
            (r) => r.command.client_uuid === p.supersedes_uuid,
        );
        if (
            !parent ||
            JSON.stringify(CommandSchema.parse(previous)) !==
                JSON.stringify(parent.command)
        )
            throw new Error("Pointer parent invalid.");
    } else if (previous !== undefined)
        throw new Error("Tagihan sudah dicatat.");
    if (
        collectionLineage(
            [...rows, item],
            item.owner,
            p.source.receivable_reference,
        ).at(-1)?.key !== item.key
    )
        throw new Error("Bukan ujung lineage.");
}
export async function validateCollectionMedia(
    item: QueueItem,
    owner: string,
    store: FieldStore,
) {
    if (item.command.type !== "collection.receipt.submit") return;
    try {
        if (item.owner !== owner) throw new Error("Owner");
        const rows = await store.list(owner),
            p = validateCollectionRows(item, rows);
        const chain = collectionLineage(
            rows,
            owner,
            p.source.receivable_reference,
        );
        const leaf = chain.at(-1)!;
        const state = async () => {
            const snapshot = await store.collectionSyncState(
                owner,
                collectionKey(p.source),
                collectionSourceKey(p.source),
            );
            assertCollectionSource(snapshot.source, p.source);
            if (
                JSON.stringify(CommandSchema.parse(snapshot.ledger)) !==
                JSON.stringify(leaf.command)
            )
                throw new Error("Ledger collection berubah/hilang.");
            const current = snapshot.rows.find((q) => q.key === item.key);
            if (
                !current ||
                JSON.stringify(current.command) !== JSON.stringify(item.command)
            )
                throw new Error("Antrean collection berubah/hilang.");
            validateCollectionRows(item, snapshot.rows);
            if (
                JSON.stringify(
                    collectionLineage(
                        snapshot.rows,
                        owner,
                        p.source.receivable_reference,
                    ),
                ) !== JSON.stringify(chain)
            )
                throw new Error("Lineage berubah saat validasi.");
        };
        await state();
        for (const ancestor of chain) {
            if (ancestor.command.type !== "collection.receipt.submit")
                throw new Error("DTO");
            const proof = ancestor.command.payload.evidence;
            const media = await store.getEvidence(owner, proof.id);
            await assertLocalEvidence(media, proof, owner);
            if (!media?.visual) throw new Error("Foto wajib paket lengkap.");
            requireVisitFix(
                {
                    latitude: proof.latitude,
                    longitude: proof.longitude,
                    accuracy: proof.accuracy,
                    sampled_at: media.visual.fixSampledAt,
                },
                p.source.delivery.site,
                Date.parse(ancestor.command.occurred_at),
            );
        }
        await state();
    } catch {
        throw new EvidenceIntegrityError(
            "Collection/tagihan/foto tidak valid; data tetap lokal dan perlu review.",
        );
    }
}
