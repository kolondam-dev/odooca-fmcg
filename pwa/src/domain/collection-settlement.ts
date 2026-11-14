import { z } from "zod";
import { normalizedReference, RupiahSchema } from "./collection-contracts.ts";
import { LocalExpenseEvidenceSchema } from "./settlement-contracts.ts";

/**
 * Penyelesaian penagihan satu toko (DS: Penagihan_toko / Penagihan_bukti / Tidak_tertagih).
 * Kontrak USULAN, belum didukung backend: PWA hanya mengirim bila `features.collection_v2 === true`.
 * Satu perintah memuat seluruh faktur yang dibayar pada satu bukti (satu nomor tanda terima, satu foto),
 * sehingga pengiriman atomik dan idempoten (client_uuid), tanpa batch multi-perintah.
 */
export const UnpaidReasonSchema = z.enum([
    "Toko tidak punya uang",
    "Pemilik tidak di tempat",
    "Menunggu retur atau potongan",
    "Sengketa faktur",
]);
export type UnpaidReason = z.infer<typeof UnpaidReasonSchema>;
const Reference = z
    .string()
    .trim()
    .min(3)
    .max(80)
    .regex(/^[A-Za-z0-9][A-Za-z0-9 /._-]*$/);
const AllocationSchema = z
    .object({
        receivable_reference: Reference,
        /** Saldo contoh saat snapshot (bukan saldo piutang Odoo). */
        amount_due: RupiahSchema,
        amount: RupiahSchema,
    })
    .strict()
    .refine((a) => BigInt(a.amount) <= BigInt(a.amount_due), {
        path: ["amount"],
        message: "Nominal melebihi saldo tagihan contoh.",
    });
const RemainderSchema = z
    .object({
        receivable_reference: Reference,
        reason: UnpaidReasonSchema,
        /** Janji bayar (tanggal). */
        promise_date: z.iso.date(),
    })
    .strict();
export const CollectionSettlementSchema = z
    .object({
        settlement_version: z.literal(1),
        outlet_id: z.string().trim().min(1).max(64),
        outlet: z.string().trim().min(1).max(200),
        trip_id: z.string().trim().min(1).max(100),
        business_date: z.iso.date(),
        /** Giro belum didukung: hanya tunai dan transfer. */
        method: z.enum(["cash", "transfer"]),
        payer: z.string().trim().min(2).max(100),
        receipt_number: Reference,
        transfer_reference: Reference.optional(),
        notes: z.string().trim().max(500),
        evidence: LocalExpenseEvidenceSchema,
        allocations: z.array(AllocationSchema).min(1).max(20),
        remainders: z.array(RemainderSchema).max(20),
    })
    .strict()
    .superRefine((p, ctx) => {
        if ((p.method === "transfer") !== !!p.transfer_reference)
            ctx.addIssue({
                code: "custom",
                path: ["transfer_reference"],
                message:
                    "Transfer wajib referensi; tunai tidak memakai referensi transfer.",
            });
        const refs = p.allocations.map((a) =>
            normalizedReference(a.receivable_reference),
        );
        if (new Set(refs).size !== refs.length)
            ctx.addIssue({
                code: "custom",
                path: ["allocations"],
                message: "Faktur ganda pada satu penyelesaian.",
            });
        // Setiap faktur yang dibayar sebagian wajib punya alasan sisa; faktur lunas tidak boleh.
        const partial = new Set(
            p.allocations
                .filter((a) => BigInt(a.amount) < BigInt(a.amount_due))
                .map((a) => normalizedReference(a.receivable_reference)),
        );
        const rem = p.remainders.map((r) =>
            normalizedReference(r.receivable_reference),
        );
        if (
            new Set(rem).size !== rem.length ||
            rem.length !== partial.size ||
            rem.some((r) => !partial.has(r))
        )
            ctx.addIssue({
                code: "custom",
                path: ["remainders"],
                message:
                    "Faktur yang dibayar sebagian wajib punya alasan sisa tidak tertagih; faktur lunas tidak.",
            });
    });
export type CollectionSettlement = z.infer<typeof CollectionSettlementSchema>;
export const COLLECTION_V2_UNSUPPORTED =
    "Server belum mendukung penagihan dari PWA. Penagihan belum dapat dikirim.";
export function collectionV2Enabled(snapshot: {
    features?: { collection_v2?: boolean };
}) {
    return snapshot.features?.collection_v2 === true;
}
/** Referensi faktur yang sudah diselesaikan (v2 tidak ditolak, atau v1 tidak ditolak) pada antrean. */
export function settledReceivables(
    rows: Array<{
        state: string;
        command: { type: string; payload?: unknown };
    }>,
) {
    const out = new Set<string>();
    for (const r of rows) {
        if (r.state === "rejected") continue;
        if (r.command.type === "collection.settlement.submit") {
            const p = r.command.payload as {
                allocations?: Array<{ receivable_reference: string }>;
            };
            for (const a of p.allocations ?? [])
                out.add(normalizedReference(a.receivable_reference));
        } else if (r.command.type === "collection.receipt.submit") {
            const p = r.command.payload as {
                source?: { receivable_reference?: string };
            };
            if (p.source?.receivable_reference)
                out.add(normalizedReference(p.source.receivable_reference));
        }
    }
    return out;
}
