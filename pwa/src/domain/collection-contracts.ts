import { z } from "zod";
import { DeliveryTaskSchema } from "./delivery-contracts.ts";
import { VisitEvidenceSchema } from "./visit-contracts.ts";
export const RupiahSchema = z.string().regex(/^[1-9][0-9]{0,11}$/);
const Reference = z
    .string()
    .trim()
    .min(3)
    .max(80)
    .regex(/^[A-Za-z0-9][A-Za-z0-9 /._-]*$/);
export const CollectionTaskSchema = z
    .object({
        delivery: DeliveryTaskSchema,
        receivable_reference: Reference,
        amount_due: RupiahSchema,
        currency: z.literal("IDR"),
        version: z.string().trim().min(1),
        issued_at: z.iso.datetime(),
        capture_allowed: z.literal(true),
    })
    .strict();
export type CollectionTask = z.infer<typeof CollectionTaskSchema>;
export const CollectionReceiptSchema = z
    .object({
        collection_version: z.literal(1),
        supersedes_uuid: z.string().uuid().optional(),
        correction_reason: z.string().trim().min(3).max(500).optional(),
        source: CollectionTaskSchema,
        payer: z.string().trim().min(2).max(100),
        method: z.enum(["cash", "transfer"]),
        amount: RupiahSchema,
        receipt_number: Reference,
        transfer_reference: Reference.optional(),
        notes: z.string().trim().max(500),
        evidence: VisitEvidenceSchema,
    })
    .strict()
    .superRefine((p, ctx) => {
        if (!!p.supersedes_uuid !== !!p.correction_reason)
            ctx.addIssue({
                code: "custom",
                message: "Koreksi wajib referensi dan alasan berpasangan.",
            });
        if ((p.method === "transfer") !== !!p.transfer_reference)
            ctx.addIssue({
                code: "custom",
                message:
                    "Transfer wajib referensi; tunai tidak memakai referensi transfer.",
            });
    });
export type CollectionReceipt = z.infer<typeof CollectionReceiptSchema>;
export const collectionKey = (s: CollectionTask) =>
    `collection-v1:${JSON.stringify([s.receivable_reference.toUpperCase().replace(/\s+/g, " ")])}`;
export const collectionSourceKey = (s: CollectionTask) =>
    `collection-manifest-v1:${s.delivery.business_date}`;
export const normalizedReference = (v: string) =>
    v
        .trim()
        .toUpperCase()
        .replace(/[ /._-]+/g, "");
