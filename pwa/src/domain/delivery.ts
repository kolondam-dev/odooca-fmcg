import {
    DeliveryPodSchema,
    DeliveryTaskSchema,
    podKey,
    type DeliveryPod,
} from "./delivery-contracts";
import { businessRejected } from "./outbox-state";
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
    if (!!p.supersedes_uuid !== !!p.correction_reason)
        throw new Error("Koreksi wajib referensi dan alasan berpasangan.");
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
    previous?: unknown,
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
    if (p.supersedes_uuid) {
        const parent = rows.find(
            (r) => r.command.client_uuid === p.supersedes_uuid,
        );
        if (
            !parent ||
            JSON.stringify(CommandSchema.parse(previous)) !==
                JSON.stringify(parent.command)
        )
            throw new Error("Pointer parent koreksi tidak cocok.");
    } else if (previous !== undefined) throw new Error("POD sudah tersimpan.");
    const chain = podLineage([...rows, item], item.owner, p.source.id);
    if (chain.at(-1)?.key !== item.key)
        throw new Error("Koreksi bukan ujung lineage.");
}
export function podLineage(rows: QueueItem[], owner: string, doId: string) {
    const all = rows.filter((r) => r.command.type === "delivery.pod.submit");
    const parsed = all.map((r) => {
        const c = CommandSchema.parse(r.command);
        if (c.type !== "delivery.pod.submit")
            throw new Error("DTO POD invalid");
        if (r.owner !== owner || r.key !== `${owner}:${c.client_uuid}`)
            throw new Error("Owner/envelope POD tidak cocok.");
        validatePod(c.payload, owner, c.occurred_at);
        return { row: r, c };
    });
    const group = parsed.filter((x) => x.c.payload.source.id === doId);
    if (!group.length) throw new Error("Lineage POD hilang.");
    const ids = new Set(parsed.map((x) => x.c.payload.evidence.id));
    if (ids.size !== parsed.length)
        throw new Error("DO/foto sudah mempunyai POD. Perlu review.");
    const roots = group.filter((x) => !x.c.payload.supersedes_uuid);
    if (roots.length !== 1) throw new Error("DO mempunyai root ganda/hilang.");
    const result: QueueItem[] = [];
    let current = roots[0];
    while (current) {
        if (result.some((r) => r.key === current.row.key))
            throw new Error("Cycle lineage POD.");
        result.push(current.row);
        const children = group.filter(
            (x) => x.c.payload.supersedes_uuid === current.c.client_uuid,
        );
        if (children.length > 1)
            throw new Error("Koreksi ganda tidak diizinkan.");
        if (!children.length) break;
        const child = children[0];
        if (
            !businessRejected(current.row) ||
            JSON.stringify(child.c.payload.source) !==
                JSON.stringify(current.c.payload.source) ||
            Date.parse(child.c.occurred_at) <
                Date.parse(current.c.occurred_at) ||
            Date.parse(child.c.payload.evidence.capturedAt) <
                Date.parse(current.c.occurred_at)
        )
            throw new Error(
                "Parent/receipt/sumber/waktu koreksi POD tidak valid.",
            );
        current = child;
    }
    if (result.length !== group.length)
        throw new Error("Parent POD hilang/cycle/sumber berbeda.");
    return result;
}

async function checkPodMedia(
    item: QueueItem,
    owner: string,
    store: FieldStore,
) {
    const c = CommandSchema.parse(item.command);
    if (c.type !== "delivery.pod.submit") return;
    const rows = await store.list(owner),
        chain = podLineage(rows, owner, c.payload.source.id);
    const current = rows.find((r) => r.key === item.key);
    if (
        !current ||
        JSON.stringify(current.command) !== JSON.stringify(item.command)
    )
        throw new Error("Antrean POD berubah.");
    const leaf = chain.at(-1)!;
    const saved = CommandSchema.parse(
        await store.draft(owner, podKey(c.payload.source)),
    );
    if (JSON.stringify(saved) !== JSON.stringify(leaf.command))
        throw new Error("Sumber POD lokal berubah/hilang.");
    for (const node of chain) {
        if (node.command.type !== "delivery.pod.submit") throw new Error("DTO");
        const p = node.command.payload;
        assertPodSource(
            await store.draft(
                owner,
                `delivery-manifest-v1:${p.source.business_date}`,
            ),
            p.source,
        );
        const media = await store.getEvidence(owner, p.evidence.id);
        await assertLocalEvidence(media, p.evidence, owner);
        if (!media?.visual) throw new Error("Paket foto POD wajib lengkap.");
        requireVisitFix(
            {
                latitude: p.evidence.latitude,
                longitude: p.evidence.longitude,
                accuracy: p.evidence.accuracy,
                sampled_at: media.visual.fixSampledAt,
            },
            p.source.site,
            Date.parse(node.command.occurred_at),
        );
    }
    const after = await store.list(owner);
    const next = podLineage(after, owner, c.payload.source.id);
    if (JSON.stringify(chain) !== JSON.stringify(next))
        throw new Error("Lineage berubah saat validasi media.");
    assertPodSource(
        await store.draft(
            owner,
            `delivery-manifest-v1:${c.payload.source.business_date}`,
        ),
        c.payload.source,
    );
    if (
        JSON.stringify(
            CommandSchema.parse(
                await store.draft(owner, podKey(c.payload.source)),
            ),
        ) !== JSON.stringify(leaf.command)
    )
        throw new Error("Sumber POD berubah saat validasi media.");
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
