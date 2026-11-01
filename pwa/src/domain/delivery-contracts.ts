import { DeliveryRequestSchema } from "./delivery-approval.ts";
import { z } from "zod";
import {
    VisitEvidenceSchema,
    VisitSiteSchema,
    VisitFixSchema,
} from "./visit-contracts.ts";
export const DeliveryDoReasonSchema = z.enum([
    "TOKO TUTUP",
    "TOKO TIDAK PUNYA UANG",
    "TOKO TIDAK DAPAT DIAKSES",
    "TOKO TIDAK ORDER",
    "ORDER MELEBIHI KEMAMPUAN TOKO",
    "SKU TIDAK SESUAI ORDER",
    "REQUEST PENDING KIRIM",
]);
export const DeliveryItemReasonSchema = z.enum([
    "ITEM RUSAK",
    "ITEM EXPIRED",
    "SALAH SKU",
    "QTY TERLALU BANYAK",
]);
export const DeliveryStatusSchema = z.enum([
    "Fully Received",
    "Received Partial",
    "Rejected",
    "Cancel Delivery",
    "Pending Requested",
]);
export const DeliverySessionSchema = z
    .object({
        id: z.string().uuid(),
        owner: z.string().min(1),
        task_id: z.string().min(1),
        opened_at: z.iso.datetime(),
        opening: VisitEvidenceSchema,
        pinpoint: VisitFixSchema,
        pinpoint_set_at: z.iso.datetime(),
        daily_source: z.unknown(),
    })
    .strict();
export const DeliveryTaskSchema = z
    .object({
        workflow_version: z.literal(2).optional(),
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
        outcome: z.enum([
            "delivered",
            "partial",
            "rejected",
            "cancel_delivery",
            "pending_requested",
        ]),
        delivery_status: DeliveryStatusSchema.optional(),
        session: DeliverySessionSchema.optional(),
        reason: z.string().trim().max(500),
        do_reason: DeliveryDoReasonSchema.optional(),
        request: DeliveryRequestSchema.optional(),
        lines: z
            .array(
                z
                    .object({
                        id: z.string().min(1),
                        received: z.number().int().nonnegative().max(9999),
                        reason: z.string().trim().max(500).optional(),
                        item_reason: DeliveryItemReasonSchema.optional(),
                        item_note: z.string().trim().max(500).optional(),
                    })
                    .strict(),
            )
            .min(1),
        evidence: VisitEvidenceSchema,
    })
    .strict()
    .superRefine((p, ctx) => {
        if (
            p.do_reason &&
            (p.outcome === "delivered" ||
                (p.do_reason === "REQUEST PENDING KIRIM" &&
                    p.outcome !== "pending_requested"))
        )
            ctx.addIssue({
                code: "custom",
                message: "Alasan DO tidak sesuai status.",
            });
        if (
            p.source.workflow_version === 2 &&
            (!p.session || !p.delivery_status)
        )
            ctx.addIssue({
                code: "custom",
                message: "POD baru wajib sesi dan status delivery.",
            });
        if (!!p.supersedes_uuid !== !!p.correction_reason)
            ctx.addIssue({
                code: "custom",
                message: "Koreksi wajib referensi dan alasan berpasangan.",
            });
    });
export type DeliveryPod = z.infer<typeof DeliveryPodSchema>;
export const podKey = (s: DeliveryTask) =>
    `delivery-pod-v1:${JSON.stringify([s.trip, s.id])}`;
