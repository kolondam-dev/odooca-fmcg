import {
    CollectionReceiptSchema,
    CollectionTaskSchema,
    collectionKey,
    collectionSourceKey,
    normalizedReference,
    type CollectionTask,
} from "./collection-contracts";
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
export function validateCollectionRows(item: QueueItem, rows: QueueItem[]) {
    const c = CommandSchema.parse(item.command);
    if (c.type !== "collection.receipt.submit")
        throw new Error("DTO collection salah.");
    const p = validateCollection(c.payload, item.owner, c.occurred_at);
    if (item.key !== `${item.owner}:${c.client_uuid}`)
        throw new Error("Envelope collection tidak cocok.");
    for (const q of rows) {
        if (q.key === item.key) continue;
        if (q.command.type !== "collection.receipt.submit") continue;
        const other = CommandSchema.parse(q.command);
        if (other.type !== "collection.receipt.submit")
            throw new Error("DTO collection invalid");
        const old = validateCollection(
            other.payload,
            item.owner,
            q.command.occurred_at,
        );
        if (
            q.owner !== item.owner ||
            q.key !== `${item.owner}:${q.command.client_uuid}` ||
            normalizedReference(old.source.receivable_reference) ===
                normalizedReference(p.source.receivable_reference) ||
            normalizedReference(old.receipt_number) ===
                normalizedReference(p.receipt_number) ||
            old.evidence.id === p.evidence.id ||
            (old.transfer_reference &&
                p.transfer_reference &&
                normalizedReference(old.transfer_reference) ===
                    normalizedReference(p.transfer_reference))
        )
            throw new Error(
                "Tagihan/nomor bukti/ref transfer/foto sudah dipakai. Perlu review.",
            );
    }
    return p;
}
export function validateCollectionCommit(
    item: QueueItem,
    key: string,
    value: unknown,
    rows: QueueItem[],
) {
    const p = validateCollectionRows(item, rows);
    if (
        key !== collectionKey(p.source) ||
        JSON.stringify(CommandSchema.parse(value)) !==
            JSON.stringify(item.command)
    )
        throw new Error("Binding collection tidak cocok.");
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
        const state = async () => {
            const snapshot = await store.collectionSyncState(
                owner,
                collectionKey(p.source),
                collectionSourceKey(p.source),
            );
            assertCollectionSource(snapshot.source, p.source);
            if (
                JSON.stringify(CommandSchema.parse(snapshot.ledger)) !==
                JSON.stringify(item.command)
            )
                throw new Error("Ledger collection berubah/hilang.");
            const current = snapshot.rows.find((q) => q.key === item.key);
            if (
                !current ||
                JSON.stringify(current.command) !== JSON.stringify(item.command)
            )
                throw new Error("Antrean collection berubah/hilang.");
            validateCollectionRows(item, snapshot.rows);
        };
        await state();
        const media = await store.getEvidence(owner, p.evidence.id);
        await assertLocalEvidence(media, p.evidence, owner);
        if (!media?.visual) throw new Error("Foto wajib paket lengkap.");
        requireVisitFix(
            {
                latitude: p.evidence.latitude,
                longitude: p.evidence.longitude,
                accuracy: p.evidence.accuracy,
                sampled_at: media.visual.fixSampledAt,
            },
            p.source.delivery.site,
            Date.parse(item.command.occurred_at),
        );
        await state();
    } catch {
        throw new EvidenceIntegrityError(
            "Collection/tagihan/foto tidak valid; data tetap lokal dan perlu review.",
        );
    }
}
