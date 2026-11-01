import { z } from "zod";

// Client draft only: server must resolve scope, evidence and approval limits.
export const ExpenseRequestSchema = z
    .object({
        category: z.enum([
            "fuel_planned",
            "fuel_emergency",
            "meal",
            "lodging",
            "repair",
            "delivery_fee",
        ]),
        amount: z
            .string()
            .regex(/^[1-9]\d{0,8}$/)
            .refine((v) => Number(v) <= 100000000),
        expense_scope: z.enum(["trip", "delivery", "outlet"]),
        trip_id: z.string().trim().min(1).max(100),
        delivery_id: z.string().trim().min(1).max(100).nullable(),
        outlet_id: z.string().trim().min(1).max(100).optional(),
        scheduled_date: z.iso.date(),
        odometer: z.number().int().min(0).max(9999999).nullable(),
        reason: z.string().trim().min(1).max(500),
        evidence: z.unknown().nullable(),
    })
    .strict();
export type ExpenseRequest = z.infer<typeof ExpenseRequestSchema>;

export function validateExpense(
    value: unknown,
    businessDate: string,
): ExpenseRequest {
    const parsed = ExpenseRequestSchema.safeParse(value);
    if (!parsed.success)
        throw new Error(
            "Lengkapi referensi trip, tanggal, nominal rupiah bulat dan alasan yang valid.",
        );
    const request = parsed.data;
    if (request.expense_scope === "delivery" && !request.delivery_id)
        throw new Error("Biaya per pengiriman wajib memiliki referensi DO.");
    if (request.expense_scope === "trip" && request.delivery_id)
        throw new Error("Biaya trip tidak boleh sekaligus dibebankan ke DO.");
    if (
        (request.expense_scope === "outlet") !== !!request.outlet_id ||
        (request.expense_scope === "outlet" && request.delivery_id)
    )
        throw new Error(
            "Biaya toko wajib referensi outlet dan tidak boleh sekaligus menjadi biaya DO.",
        );
    if (request.category.startsWith("fuel") && request.odometer === null)
        throw new Error("BBM wajib mencatat KM awal.");
    if (request.category === "fuel_planned") {
        if (!z.iso.date().safeParse(businessDate).success)
            throw new Error(
                "Tanggal bisnis belum tersedia. Sync ulang sebelum mengajukan BBM H-1.",
            );
        const tomorrow = new Date(`${businessDate}T00:00:00Z`);
        tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
        if (request.scheduled_date !== tomorrow.toISOString().slice(0, 10))
            throw new Error(
                "BBM terencana wajib diajukan H-1. Untuk kebutuhan hari ini gunakan BBM insidentil.",
            );
    }
    return request;
}
