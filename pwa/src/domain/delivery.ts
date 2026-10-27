import {
    DeliveryPodSchema,
    DeliveryTaskSchema,
    podKey,
    type DeliveryPod,
} from "./delivery-contracts";
import { requireVisitFix } from "./visit-validation";
import {
    assertLocalEvidence,
    EvidenceIntegrityError,
} from "./evidence-package";
import type { FieldStore, QueueItem } from "../storage/store";
import { CommandSchema } from "./contracts";
export function validatePod(
    value: unknown,
    owner: string,
    at: string,
): DeliveryPod {
    const p = DeliveryPodSchema.parse(value),
        s = p.source;
    if (
        s.owner !== owner ||
        new Date(at).toLocaleDateString("en-CA", {
            timeZone: "Asia/Makassar",
        }) !== s.business_date
    )
        throw new Error("Manifest bukan milik petugas/hari kejadian ini.");
    if (
        new Set(s.lines.map((l) => l.id)).size !== s.lines.length ||
        p.lines.length !== s.lines.length ||
        new Set(p.lines.map((l) => l.id)).size !== p.lines.length
    )
        throw new Error("Item manifest tidak cocok.");
    let total = 0,
        expected = 0;
    for (const l of s.lines) {
        const a = p.lines.find((a) => a.id === l.id);
        if (!a || a.received > l.quantity)
            throw new Error("Kuantitas melebihi manifest/item berubah.");
        total += a.received;
        expected += l.quantity;
    }
    if (
        (p.outcome === "delivered" && total !== expected) ||
        (p.outcome === "partial" && !(total > 0 && total < expected)) ||
        (p.outcome === "rejected" && total !== 0)
    )
        throw new Error("Hasil tidak sesuai kuantitas diterima.");
    if (p.outcome !== "delivered" && p.reason.length < 3)
        throw new Error("Selisih/penolakan wajib alasan.");
    requireVisitFix(
        {
            latitude: p.evidence.latitude,
            longitude: p.evidence.longitude,
            accuracy: p.evidence.accuracy,
            sampled_at: p.evidence.capturedAt,
        },
        s.site,
        Date.parse(at),
    );
    return p;
}
export function validatePodCommit(
    item: QueueItem,
    key: string,
    value: unknown,
    rows: QueueItem[],
) {
    if (item.command.type !== "delivery.pod.submit") return;
    const p = validatePod(
        item.command.payload,
        item.owner,
        item.command.occurred_at,
    );
    if (
        key !== podKey(p.source) ||
        JSON.stringify(CommandSchema.parse(value)) !==
            JSON.stringify(item.command)
    )
        throw new Error("Binding POD tidak cocok.");
    for (const row of rows) {
        if (row.command.type !== "delivery.pod.submit") continue;
        const old = DeliveryPodSchema.parse(row.command.payload);
        if (old.source.id === p.source.id || old.evidence.id === p.evidence.id)
            throw new Error(
                "DO/foto sudah mempunyai POD. Perlu review, bukan kirim ulang.",
            );
    }
}
async function checkPodMedia(
    item: QueueItem,
    owner: string,
    store: FieldStore,
) {
    const c = CommandSchema.parse(item.command);
    if (c.type !== "delivery.pod.submit") return;
    if (item.owner !== owner || item.key !== `${owner}:${c.client_uuid}`)
        throw new Error("Owner/envelope POD tidak cocok.");
    const p = validatePod(c.payload, owner, c.occurred_at);
    assertPodSource(
        await store.draft(
            owner,
            `delivery-manifest-v1:${p.source.business_date}`,
        ),
        p.source,
    );
    const saved = await store.draft(owner, podKey(p.source));
    if (JSON.stringify(CommandSchema.parse(saved)) !== JSON.stringify(c))
        throw new Error("Sumber POD lokal berubah/hilang. Perlu review.");
    const row = await store.getEvidence(owner, p.evidence.id);
    await assertLocalEvidence(row, p.evidence, owner);
    if (!row?.visual) throw new Error("Paket foto POD wajib lengkap.");
    requireVisitFix(
        {
            latitude: p.evidence.latitude,
            longitude: p.evidence.longitude,
            accuracy: p.evidence.accuracy,
            sampled_at: row.visual.fixSampledAt,
        },
        p.source.site,
        Date.parse(c.occurred_at),
    );
    assertPodSource(
        await store.draft(
            owner,
            `delivery-manifest-v1:${p.source.business_date}`,
        ),
        p.source,
    );
    if (
        JSON.stringify(
            CommandSchema.parse(await store.draft(owner, podKey(p.source))),
        ) !== JSON.stringify(c)
    )
        throw new Error("Sumber POD berubah saat validasi media.");
    const rows = await store.list(owner);
    const current = rows.find((r) => r.key === item.key);
    if (
        !current ||
        JSON.stringify(current.command) !== JSON.stringify(item.command)
    )
        throw new Error("Antrean POD berubah saat validasi media.");
    if (
        rows.some(
            (r) =>
                r.key !== item.key &&
                r.command.type === "delivery.pod.submit" &&
                (r.command.payload.source.id === p.source.id ||
                    r.command.payload.evidence.id === p.evidence.id),
        )
    )
        throw new Error("POD/foto duplikat dalam antrean.");
}

export function assertPodSource(value: unknown, source: DeliveryPod["source"]) {
    if (
        !Array.isArray(value) ||
        !value.some(
            (v) =>
                JSON.stringify(DeliveryTaskSchema.parse(v)) ===
                JSON.stringify(source),
        )
    )
        throw new Error("Manifest sumber berubah/hilang. Perlu review.");
}

export async function validatePodMedia(
    item: QueueItem,
    owner: string,
    store: FieldStore,
) {
    if (item.command.type !== "delivery.pod.submit") return;
    try {
        await checkPodMedia(item, owner, store);
    } catch {
        throw new EvidenceIntegrityError(
            "POD/manifest/foto tidak valid; data tetap lokal dan perlu review.",
        );
    }
}
