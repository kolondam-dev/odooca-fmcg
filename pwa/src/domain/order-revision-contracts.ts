import { z } from "zod";
import { UomSchema, DiscountRequestSchema } from "./order-pricing.ts";
export const OrderRevisionSchema = z
    .object({
        revision_version: z.literal(1),
        root_uuid: z.string().uuid(),
        supersedes_uuid: z.string().uuid(),
        correction_reason: z.string().trim().min(3).max(500),
        outlet_id: z.string().min(1),
        snapshot_version: z.string().min(1),
        business_date: z.iso.date(),
        daily_source: z.unknown(),
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
        pricing_version: z.literal(1),
        discount_request: DiscountRequestSchema.optional(),
        observed_total: z.string().regex(/^\d+$/),
    })
    .strict();
export type OrderRevision = z.infer<typeof OrderRevisionSchema>;
export const revisionKey = (root: string) => `sales-order-revision-v1:${root}`;
