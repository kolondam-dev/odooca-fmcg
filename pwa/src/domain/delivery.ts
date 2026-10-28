import { DeliverySessionSchema } from "./delivery-contracts";
import { MorningRecordSchema, morningReady } from "./morning";
export const DELIVERY_SESSION_KEY = "delivery-active-session-v2";
export const statusOutcome = {
    "Fully Received": "delivered",
    "Received Partial": "partial",
    Rejected: "rejected",
    "Cancel Delivery": "cancel_delivery",
    "Pending Requested": "pending_requested",
} as const;
export function validateDeliverySession(
    raw: unknown,
    source: DeliveryPod["source"],
    owner: string,
    at: string,
) {
    const session = DeliverySessionSchema.parse(raw);
    const daily = MorningRecordSchema.parse(session.daily_source);
    if (
        session.owner !== owner ||
        session.task_id !== source.id ||
        !morningReady(daily, owner, source.business_date) ||
        !daily.deliveryManifest?.some(
            (t) => JSON.stringify(t) === JSON.stringify(source),
        ) ||
        Date.parse(session.opening.capturedAt) < Date.parse(daily.openedAt!) ||
        Date.parse(session.opened_at) < Date.parse(daily.openedAt!) ||
        Date.parse(session.opened_at) > Date.parse(at) ||
        Date.parse(session.opened_at) - Date.parse(session.opening.capturedAt) <
            0 ||
        Date.parse(session.opened_at) - Date.parse(session.opening.capturedAt) >
            60000
    )
        throw new Error("Sesi delivery/daily sync/foto opening tidak valid.");
    requireVisitFix(
        session.pinpoint,
        source.site,
        Date.parse(session.opened_at),
    );
    if (
        Date.parse(session.pinpoint_set_at) <
            Date.parse(session.opening.capturedAt) ||
        Date.parse(session.pinpoint_set_at) > Date.parse(session.opened_at)
    )
        throw new Error("Set pinpoint setelah foto toko.");
    requireVisitFix(
        {
            latitude: session.opening.latitude,
            longitude: session.opening.longitude,
            accuracy: session.opening.accuracy,
            sampled_at: session.opening.capturedAt,
        },
        source.site,
        Date.parse(session.opened_at),
    );
    return session;
}
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
    if (s.workflow_version === 2) {
        const session = validateDeliverySession(p.session, s, owner, at);
        if (
            !p.delivery_status ||
            statusOutcome[p.delivery_status] !== p.outcome ||
            p.evidence.id === session.opening.id ||
            Date.parse(p.evidence.capturedAt) < Date.parse(session.opened_at)
        )
            throw new Error("Status/foto closing sesi delivery tidak valid.");
        if (p.outcome !== "partial" && p.reason.trim().length < 3)
            throw new Error("Status wajib alasan minimal 3 karakter.");
        for (const l of s.lines) {
            const a = p.lines.find((a) => a.id === l.id);
            if (
                !a ||
                (p.outcome === "partial"
                    ? a.received < l.quantity &&
                      (a.reason?.trim().length ?? 0) < 3
                    : a.reason !== p.reason.trim())
            )
                throw new Error("Alasan wajib direkam pada item terkait.");
        }
    }
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
        (["rejected", "cancel_delivery", "pending_requested"].includes(
            p.outcome,
        ) &&
            total !== 0)
    )
        throw new Error("Hasil tidak sesuai kuantitas diterima.");
    if (
        s.workflow_version !== 2 &&
        p.outcome !== "delivered" &&
        p.reason.length < 3
    )
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
    const mediaIds = parsed.flatMap((x) => [
        x.c.payload.evidence.id,
        ...(x.c.payload.session ? [x.c.payload.session.opening.id] : []),
    ]);
    const ids = new Set(mediaIds);
    if (ids.size !== mediaIds.length)
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
        if (p.source.workflow_version === 2) {
            const session = validateDeliverySession(
                p.session,
                p.source,
                owner,
                node.command.occurred_at,
            );
            const opening = await store.getEvidence(owner, session.opening.id);
            await assertLocalEvidence(opening, session.opening, owner);
            if (!opening?.visual) throw new Error("Paket opening hilang.");
            requireVisitFix(
                {
                    latitude: session.opening.latitude,
                    longitude: session.opening.longitude,
                    accuracy: session.opening.accuracy,
                    sampled_at: opening.visual.fixSampledAt,
                },
                p.source.site,
                Date.parse(session.opened_at),
            );
        }
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
