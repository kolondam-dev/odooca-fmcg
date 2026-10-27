import { z } from "zod";
import { VisitEvidenceSchema, VisitSiteSchema } from "./visit-contracts.ts";
export const DeliveryTaskSchema = z
    .object({
        id: z.string().min(1),
        trip: z.string().min(1),
        vehicle: z.string().min(1),
        outlet: z.string().min(1),
        outlet_id: z.string().min(1),
        address: z.string(),
        owner: z.string().min(1),
        business_date: z.iso.date(),
        version: z.string().min(1),
        site: VisitSiteSchema,
        lines: z
            .array(
                z
                    .object({
                        id: z.string().min(1),
                        name: z.string().min(1),
                        quantity: z.number().int().positive().max(9999),
                        unit: z.string().min(1),
                    })
                    .strict(),
            )
            .min(1),
    })
    .strict();
export type DeliveryTask = z.infer<typeof DeliveryTaskSchema>;
export const DeliveryPodSchema = z
    .object({
        pod_version: z.literal(1),
        supersedes_uuid: z.string().uuid().optional(),
        correction_reason: z.string().trim().min(3).max(500).optional(),
        source: DeliveryTaskSchema,
        recipient: z.string().trim().min(2).max(100),
        outcome: z.enum(["delivered", "partial", "rejected"]),
        reason: z.string().trim().max(500),
        lines: z
            .array(
                z
                    .object({
                        id: z.string().min(1),
                        received: z.number().int().nonnegative().max(9999),
                    })
                    .strict(),
            )
            .min(1),
        evidence: VisitEvidenceSchema,
    })
    .strict()
    .superRefine((p, ctx) => {
        if (!!p.supersedes_uuid !== !!p.correction_reason)
            ctx.addIssue({
                code: "custom",
                message: "Koreksi wajib referensi dan alasan berpasangan.",
            });
    });
export type DeliveryPod = z.infer<typeof DeliveryPodSchema>;
export const podKey = (s: DeliveryTask) =>
    `delivery-pod-v1:${JSON.stringify([s.trip, s.id])}`;
