import {
    VisitEvidenceSchema,
    type VisitEvidence,
    type VisitContext,
} from "./visit-contracts";
import {
    assertLocalEvidence,
    type EvidenceReference,
} from "./evidence-package";
import { requireVisitFix } from "./visit-validation";
import { CommandSchema, type Command } from "./contracts";
import type { FieldStore, QueueItem } from "../storage/store";
export function bindVisitEvidence(
    value: unknown,
    context: VisitContext,
    at: string,
    notBefore: string,
): VisitEvidence {
    const parsed = VisitEvidenceSchema.safeParse(value);
    if (!parsed.success)
        throw new Error("Simpan paket foto kunjungan sebelum melakukan aksi.");
    const ref = parsed.data;
    if (
        Date.parse(ref.capturedAt) < Date.parse(notBefore) ||
        Date.parse(ref.capturedAt) > Date.parse(at)
    )
        throw new Error(
            "Waktu foto tidak sesuai sesi/aksi kunjungan. Ambil foto baru.",
        );
    requireVisitFix(
        {
            latitude: ref.latitude,
            longitude: ref.longitude,
            accuracy: ref.accuracy,
            sampled_at: ref.capturedAt,
        },
        context.site,
        Date.parse(at),
    );
    return ref;
}
export async function assertVisitEvidence(
    ref: EvidenceReference,
    context: VisitContext,
    at: string,
    owner: string,
    store: FieldStore,
) {
    const row = await store.getEvidence(owner, ref.id);
    await assertLocalEvidence(row, ref, owner);
    if (!row?.visual)
        throw new Error(
            "Kunjungan baru wajib paket foto lengkap; perlu review.",
        );
    requireVisitFix(
        {
            latitude: ref.latitude,
            longitude: ref.longitude,
            accuracy: ref.accuracy,
            sampled_at: row.visual.fixSampledAt,
        },
        context.site,
        Date.parse(at),
    );
}
// Include accepted ancestors: a receipt never exempts damaged local media.
export async function validateVisitMedia(
    rows: QueueItem[],
    owner: string,
    store: FieldStore,
    visitId?: string,
) {
    for (const row of rows) {
        if (
            row.owner !== owner ||
            !["sales.visit.check_in", "sales.visit.check_out"].includes(
                row.command.type,
            )
        )
            continue;
        const command = CommandSchema.parse(row.command);
        if (
            command.type !== "sales.visit.check_in" &&
            command.type !== "sales.visit.check_out"
        )
            continue;
        if (visitId && command.payload.visit_uuid !== visitId) continue;
        if (!command.payload.evidence_version) continue; // explicit persisted legacy path
        await assertVisitEvidence(
            command.payload.evidence!,
            command.payload,
            command.occurred_at,
            owner,
            store,
        );
    }
}
export function visitIdForMedia(command: Command): string | undefined {
    if (
        command.type === "sales.visit.check_in" ||
        command.type === "sales.visit.check_out"
    )
        return command.payload.visit_uuid;
    if (
        command.type === "sales.order.submit" &&
        command.payload.visit_context
    ) {
        const v = command.payload.visit_context as VisitContext;
        return v.visit_uuid;
    }
}
