import { z } from "zod";

// Client draft only: server must resolve scope, evidence and approval limits.
export const ExpenseRequestSchema = z
    .object({
        category: z.enum([
            // Kategori mockup (Ajukan_uang): BBM, Makan, Nginap, Darurat.
            "fuel",
            "meal",
            "lodging",
            "emergency",
            // Biaya operasional toko (Biaya_toko), scope outlet.
            "store_parking",
            "store_unloading",
            "store_levy",
            "store_other",
            // Legacy (antrean/riwayat lama + biaya toko/DO).
            "fuel_planned",
            "fuel_emergency",
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
/** BBM v2 mencatat KM saat realisasi (bukan saat pengajuan). */
export const needsRequestOdometer = (category: string) =>
    category.startsWith("fuel_");
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
    if (needsRequestOdometer(request.category) && request.odometer === null)
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

/** Gerbang kontrak: backend belum menyatakan dukungan kategori/payload baru -> pengajuan dikunci. */
export const FIELD_EXPENSE_V2_UNSUPPORTED =
    "Server belum mendukung pengajuan uang lapangan format baru. Pengajuan belum dapat dikirim.";
export function fieldExpenseV2Enabled(snapshot: {
    features?: { field_expense_v2?: boolean };
}) {
    return snapshot.features?.field_expense_v2 === true;
}

/** Gerbang kontrak biaya operasional toko (kategori `store_*`). */
export const OUTLET_EXPENSE_UNSUPPORTED =
    "Server belum mendukung biaya operasional toko dari PWA. Biaya belum dapat dikirim.";
export function outletExpenseEnabled(snapshot: {
    features?: { outlet_expense_v1?: boolean };
}) {
    return snapshot.features?.outlet_expense_v1 === true;
}
