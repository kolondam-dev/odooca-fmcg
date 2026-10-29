import { z } from "zod";
const rupiah = z
    .string()
    .regex(/^[1-9]\d{0,8}$/)
    .refine((v) => Number(v) <= 100000000);
export const ExpensePolicySchema = z
    .object({ version: z.string().trim().min(1), supervisor_limit: rupiah })
    .strict();
export const LocalExpenseEvidenceSchema = z
    .object({
        id: z.string().uuid(),
        packageHash: z
            .string()
            .regex(/^[a-f0-9]{64}$/)
            .optional(),
        latitude: z.number().min(-90).max(90),
        longitude: z.number().min(-180).max(180),
        accuracy: z.number().nonnegative(),
        capturedAt: z.iso.datetime(),
    })
    .strict();
export const ExpenseRealizationSchema = z
    .object({
        supersedes_uuid: z.string().uuid().optional(),
        correction_reason: z.string().trim().min(5).max(500).optional(),
        source_request_uuid: z.string().uuid(),
        advance_reference: z.string().min(1),
        lines: z
            .array(
                z
                    .object({
                        description: z.string().trim().min(1).max(200),
                        amount: rupiah,
                        merchant: z.string().trim().min(1).max(100),
                        receipt_number: z.string().trim().min(1).max(100),
                        expense_date: z.iso.date(),
                        evidence: LocalExpenseEvidenceSchema,
                    })
                    .strict(),
            )
            .min(1)
            .max(10),
        fuel: z
            .object({
                liters: z.string().regex(/^(?:0|[1-9]\d{0,3})(?:\.\d{1,3})?$/),
                price_per_liter: rupiah,
                odometer_before: z.number().int().min(0).max(9999999),
                odometer_after: z.number().int().min(0).max(9999999),
                before: LocalExpenseEvidenceSchema,
                after: LocalExpenseEvidenceSchema,
            })
            .strict()
            .nullable(),
        evidence_status: z.literal("local_map_pending"),
    })
    .strict();
export type ExpenseRealization = z.infer<typeof ExpenseRealizationSchema>;
export type ExpensePolicy = z.infer<typeof ExpensePolicySchema>;
export const SimulatedAdvanceSchema = z
    .object({
        mode: z.literal("simulation"),
        owner: z.string().min(1),
        source_request_uuid: z.string().uuid(),
        request_fingerprint: z.string().min(1),
        reference: z.string().min(1),
        amount: rupiah,
        policy: ExpensePolicySchema,
        approvals: z.array(z.enum(["supervisor", "branch_manager"])).min(1),
        approved_at: z.iso.datetime(),
        disbursed_at: z.iso.datetime(),
        realization_uuid: z.string().uuid().nullable(),
    })
    .strict();
export type SimulatedAdvance = z.infer<typeof SimulatedAdvanceSchema>;

export function receiptKey(line: {
    merchant: string;
    receipt_number: string;
    expense_date: string;
}): string {
    return JSON.stringify([
        line.merchant.trim().normalize("NFKC").toUpperCase(),
        line.receipt_number.trim().normalize("NFKC").toUpperCase(),
        line.expense_date,
    ]);
}
