import { validateVisitMedia, visitIdForMedia } from "./visit-evidence";
import { z } from "zod";
import { LocalExpenseEvidenceSchema } from "./settlement-contracts";
import type { Evidence, FieldStore } from "../storage/store";
import type { Command } from "./contracts";
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const VisualEvidenceSchema = z
    .object({
        version: z.literal(1),
        kind: z.literal("simulation_grid"),
        selectedAt: z.iso.datetime(),
        fixSampledAt: z.iso.datetime(),
        photoSha256: hash,
        mapSha256: hash,
        bindingSha256: hash,
    })
    .strict();
export type VisualEvidence = z.infer<typeof VisualEvidenceSchema> & {
    map: Blob;
};
export type EvidenceReference = z.infer<typeof LocalExpenseEvidenceSchema>;
export async function sha256(blob: Blob | string) {
    const bytes =
        typeof blob === "string"
            ? new TextEncoder().encode(blob)
            : await blob.arrayBuffer();
    return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
}
export function evidenceBinding(
    row: Evidence,
    visual: Omit<z.infer<typeof VisualEvidenceSchema>, "bindingSha256">,
) {
    return JSON.stringify({
        owner: row.owner,
        key: row.key,
        capturedAt: row.capturedAt,
        latitude: row.latitude,
        longitude: row.longitude,
        accuracy: row.accuracy,
        mapStatus: row.mapStatus,
        ...visual,
    });
}
export function validateEvidenceTime(
    ref: EvidenceReference,
    selectedAt: string,
    fixSampledAt: string,
) {
    if (!LocalExpenseEvidenceSchema.safeParse(ref).success)
        throw new Error(
            "Koordinat/metadata bukti tidak valid. Ambil ulang foto dan lokasi.",
        );
    const saved = Date.parse(ref.capturedAt),
        selected = Date.parse(selectedAt),
        fix = Date.parse(fixSampledAt);
    if (
        ![saved, selected, fix].every(Number.isFinite) ||
        ref.accuracy <= 0 ||
        ref.accuracy > 10000 ||
        saved - selected < 0 ||
        saved - selected > 300000 ||
        saved - fix > 60000 ||
        fix - saved > 1000
    )
        throw new Error(
            "Waktu/akurasi bukti tidak valid. Ambil ulang foto dan lokasi.",
        );
}
export async function assertLocalEvidence(
    row: Evidence | undefined,
    ref: EvidenceReference,
    owner: string,
) {
    if (
        !row ||
        row.owner !== owner ||
        row.key !== `${owner}:${ref.id}` ||
        row.capturedAt !== ref.capturedAt ||
        row.latitude !== ref.latitude ||
        row.longitude !== ref.longitude ||
        row.accuracy !== ref.accuracy ||
        row.mapStatus !== "pending" ||
        !(row.blob instanceof Blob) ||
        !row.blob.size
    )
        throw new Error(
            "Foto lokal tidak ditemukan atau metadata bukti tidak cocok. Ambil ulang bukti.",
        );
    if (row.visual === undefined && ref.packageHash === undefined) return; // explicit legacy path
    if (!row.visual || !ref.packageHash)
        throw new Error("Paket bukti lokal hilang/tidak cocok; perlu review.");
    const { map, ...raw } = row.visual;
    const parsed = VisualEvidenceSchema.safeParse(raw);
    if (!parsed.success)
        throw new Error("Metadata paket bukti tidak valid; perlu review.");
    const visual = parsed.data;
    validateEvidenceTime(ref, visual.selectedAt, visual.fixSampledAt);
    if (
        row.blob.type !== "image/jpeg" ||
        row.blob.size > 1024 * 1024 ||
        !(map instanceof Blob) ||
        map.type !== "image/png" ||
        !map.size ||
        map.size > 128 * 1024 ||
        Date.parse(ref.capturedAt) > Date.now() + 1000
    )
        throw new Error("Format/waktu paket bukti tidak valid; perlu review.");
    const { bindingSha256, ...source } = visual;
    if (
        bindingSha256 !== ref.packageHash ||
        (await sha256(evidenceBinding(row, source))) !== bindingSha256 ||
        (await sha256(row.blob)) !== visual.photoSha256 ||
        (await sha256(map)) !== visual.mapSha256
    )
        throw new Error(
            "Isi foto/snapshot/metadata berubah; paket bukti perlu review.",
        );
}
class EvidenceIntegrityError extends Error {}
export { EvidenceIntegrityError };
export async function validatePackagedCommandEvidence(
    command: Command,
    owner: string,
    store: FieldStore,
) {
    try {
        const visitId = visitIdForMedia(command);
        if (visitId)
            await validateVisitMedia(
                await store.list(owner),
                owner,
                store,
                visitId,
            );
        const candidates: unknown[] =
            command.type === "field_expense.realization.submit"
                ? [
                      ...command.payload.lines.map((l) => l.evidence),
                      ...(command.payload.fuel
                          ? [
                                command.payload.fuel.before,
                                command.payload.fuel.after,
                            ]
                          : []),
                  ]
                : [
                      "evidence" in command.payload
                          ? command.payload.evidence
                          : undefined,
                  ];
        // Legacy references are not upgraded or falsely claimed to have a package.
        for (const value of candidates) {
            if (!value || typeof value !== "object") continue;
            const raw = value as Record<string, unknown>;
            const found =
                typeof raw.id === "string"
                    ? await store.getEvidence(owner, raw.id)
                    : undefined;
            if (
                !Object.hasOwn(raw, "packageHash") &&
                found?.visual === undefined
            )
                continue;
            await assertLocalEvidence(
                found,
                LocalExpenseEvidenceSchema.parse(value),
                owner,
            );
        }
    } catch {
        throw new EvidenceIntegrityError(
            "Paket bukti perlu review; data tetap lokal.",
        );
    }
}
