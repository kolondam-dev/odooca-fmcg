import { UomSchema, DiscountRequestSchema } from "./order-pricing.ts";
import { z } from "zod";
import { LocalExpenseEvidenceSchema } from "./settlement-contracts.ts";
export const VisitEvidenceSchema = LocalExpenseEvidenceSchema.extend({
    packageHash: z.string().regex(/^[a-f0-9]{64}$/),
});
export type VisitEvidence = z.infer<typeof VisitEvidenceSchema>;
const photoFields = {
    evidence_version: z.literal(1).optional(),
    evidence: VisitEvidenceSchema.optional(),
};
export function photoPair(
    value: { evidence_version?: 1; evidence?: VisitEvidence },
    ctx: z.RefinementCtx,
) {
    if ((value.evidence_version === 1) !== !!value.evidence)
        ctx.addIssue({
            code: "custom",
            message: "Versi dan paket foto kunjungan wajib berpasangan",
        });
}
export const VisitFixSchema = z
    .object({
        latitude: z.number().min(-90).max(90),
        longitude: z.number().min(-180).max(180),
        accuracy: z.number().positive(),
        sampled_at: z.iso.datetime(),
    })
    .strict();
export const VisitSiteSchema = z
    .object({
        latitude: z.number().min(-90).max(90),
        longitude: z.number().min(-180).max(180),
        radius: z.number().min(5).max(15),
        demo_unrestricted: z.literal(true).optional(),
    })
    .strict();
export const VisitContextSchema = z
    .object({
        visit_uuid: z.string().uuid(),
        work_session_id: z.string().uuid(),
        business_date: z.iso.date(),
        snapshot_version: z.string().trim().min(1),
        outlet_id: z.string().min(1),
        site: VisitSiteSchema,
        fix: VisitFixSchema,
    })
    .strict();
export const VisitCheckInSchema =
    VisitContextSchema.extend(photoFields).superRefine(photoPair);
export const VisitCheckoutSchema = VisitContextSchema.extend({
    ...photoFields,
    outcome: z.enum([
        "order_requested",
        "no_order",
        "outlet_closed",
        "unavailable",
    ]),
    notes: z.string().trim().max(500),
    order_uuids: z.array(z.string().uuid()),
})
    .strict()
    .superRefine(photoPair);
export const VisitRecordSchema = z
    .object({
        mode: z.literal("simulation"),
        owner: z.string().min(1),
        context: VisitContextSchema,
        session_opened_at: z.iso.datetime(),
        morning_source: z.unknown().optional(),
        check_in_at: z.iso.datetime(),
        photo_required: z.literal(true).optional(),
        check_in_evidence: VisitEvidenceSchema.optional(),
        check_out: z
            .object({
                command_uuid: z.string().uuid(),
                occurred_at: z.iso.datetime(),
                payload: VisitCheckoutSchema,
            })
            .strict()
            .nullable(),
    })
    .strict();
export const VisitLedgerSchema = z
    .object({ version: z.literal(1), visits: z.array(VisitRecordSchema) })
    .strict();
export type VisitFix = z.infer<typeof VisitFixSchema>;
export type VisitContext = z.infer<typeof VisitContextSchema>;
export type VisitCheckout = z.infer<typeof VisitCheckoutSchema>;
export type VisitRecord = z.infer<typeof VisitRecordSchema>;
export type VisitLedger = z.infer<typeof VisitLedgerSchema>;

export const VisitOrderSchema = z
    .object({
        outlet_id: z.string().min(1),
        work_session_id: z.string().uuid(),
        morning_business_date: z.iso.date(),
        snapshot_version: z.string().min(1),
        lines: z
            .array(
                z
                    .object({
                        product_id: z.string().min(1),
                        qty: z.string().regex(/^[1-9]\d{0,2}$/),
                        uom: UomSchema,
                    })
                    .strict(),
            )
            .min(1)
            .max(500),
        note: z.string().max(500),
        observed_total: z.string().regex(/^\d+$/),
        pricing_version: z.literal(1).optional(),
        discount_request: DiscountRequestSchema.optional(),
        visit_context: VisitContextSchema,
    })
    .strict();
