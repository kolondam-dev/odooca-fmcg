import { z } from "zod";

const step = z.object({
    name: z.string(),
    state: z.string(),
    actor: z.string(),
    notes: z.string(),
});
export const AttendanceApprovalSchema = z.object({
    id: z.number().int(),
    reference: z.string(),
    reason: z.string(),
    state: z.string(),
    tier: z.number().int(),
    canDecide: z.boolean(),
    mine: z.boolean(),
    steps: z.array(step),
});
export const AttendanceInboxSchema = z.object({
    items: z.array(AttendanceApprovalSchema),
    csrfToken: z.string(),
});
