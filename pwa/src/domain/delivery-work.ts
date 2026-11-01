import { z } from "zod";
import {
    DeliveryTaskSchema,
    DeliveryDoReasonSchema,
    DeliveryItemReasonSchema,
    type DeliveryTask,
} from "./delivery-contracts";
import { CancelReasonSchema } from "./delivery-approval";
export const DeliveryWorkSchema = z
    .object({
        source: DeliveryTaskSchema,
        recipient: z.string().max(100),
        outcome: z.enum([
            "delivered",
            "partial",
            "rejected",
            "cancel_delivery",
            "pending_requested",
        ]),
        reason: z.string().max(500),
        doReason: z.union([z.literal(""), DeliveryDoReasonSchema]).default(""),
        requestedDate: z.union([z.literal(""), z.iso.date()]),
        cancelReason: CancelReasonSchema,
        lines: z.array(
            z
                .object({
                    id: z.string(),
                    received: z.number().int().nonnegative(),
                    reason: z.string().max(500),
                    item_reason: DeliveryItemReasonSchema.optional(),
                })
                .strict(),
        ),
    })
    .strict();
export const deliveryWorkKey = (task: DeliveryTask) =>
    `delivery-work-v1:${JSON.stringify([task.trip, task.id, task.business_date, task.version])}`;
export function restoreDeliveryWork(value: unknown, task: DeliveryTask) {
    const parsed = DeliveryWorkSchema.parse(value);
    if (
        JSON.stringify(parsed.source) !==
        JSON.stringify(DeliveryTaskSchema.parse(task))
    )
        throw new Error("Sumber draft penerimaan berubah. Perlu review.");
    if (
        parsed.lines.length !== task.lines.length ||
        new Set(parsed.lines.map((line) => line.id)).size !==
            task.lines.length ||
        parsed.lines.some(
            (line) =>
                !task.lines.some(
                    (source) =>
                        source.id === line.id &&
                        line.received <= source.quantity,
                ),
        )
    )
        throw new Error("Item draft penerimaan tidak cocok dengan DO.");
    // Render by manifest order; user-supplied draft order never changes SKU binding.
    return {
        ...parsed,
        lines: task.lines.map(
            (line) => parsed.lines.find((value) => value.id === line.id)!,
        ),
    };
}
export function receivedOutcome(
    lines: { received: number }[],
    source: DeliveryTask["lines"],
) {
    const total = lines.reduce((sum, line) => sum + line.received, 0),
        expected = source.reduce((sum, line) => sum + line.quantity, 0);
    return total === expected
        ? "delivered"
        : total === 0
          ? "rejected"
          : "partial";
}
