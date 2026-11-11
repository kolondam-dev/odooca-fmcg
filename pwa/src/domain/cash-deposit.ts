import { z } from "zod";

/**
 * Setor uang ke kasir (DS: Setor_uang). Kontrak USULAN, belum didukung backend:
 * PWA hanya mengirim bila `features.cash_deposit_v1 === true`.
 */
export const CashDepositSchema = z
    .object({
        deposit_version: z.literal(1),
        trip_id: z.string().trim().min(1).max(100),
        business_date: z.iso.date(),
        /** Total tunai kuitansi trip (bukan ditolak, bukan terkoreksi). */
        cash_expected: z.string().regex(/^(0|[1-9]\d{0,11})$/),
        cash_deposited: z.string().regex(/^[1-9]\d{0,11}$/),
        difference_note: z.string().trim().max(500).optional(),
        /** client_uuid kuitansi tunai yang disetor. */
        receipt_uuids: z.array(z.string().uuid()).max(200),
        /** Paket bukti foto setor (EvidenceRef). */
        evidence: z.unknown().refine((v) => !!v, "Foto bukti setor wajib."),
    })
    .strict()
    .superRefine((p, ctx) => {
        if (
            p.cash_expected !== p.cash_deposited &&
            (p.difference_note ?? "").length < 3
        )
            ctx.addIssue({
                code: "custom",
                path: ["difference_note"],
                message: "Selisih setoran wajib dijelaskan di catatan.",
            });
    });
export type CashDeposit = z.infer<typeof CashDepositSchema>;
export const CASH_DEPOSIT_UNSUPPORTED =
    "Server belum mendukung setoran kasir dari PWA. Setoran belum dapat dikirim.";
export function cashDepositEnabled(snapshot: {
    features?: { cash_deposit_v1?: boolean };
}) {
    return snapshot.features?.cash_deposit_v1 === true;
}
