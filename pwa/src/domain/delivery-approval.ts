import { z } from "zod";
export const CancelReasonSchema = z.enum([
    "Toko Tutup",
    "Kemasan basah/penyok saat handling transit",
    "Produk mendekati kadaluarsa / Expired",
    "Salah kirim SKU / kuantitas lebih",
    "Toko tutup / menolak menerima pesanan",
    "Kesalahan Order",
    "Tidak bisa bayar",
    "Toko tidak dapat diakses",
    "Waktu pengiriman tidak cukup",
]);
export const DeliveryRequestSchema = z.discriminatedUnion("kind", [
    z
        .object({ kind: z.literal("reschedule"), requested_date: z.iso.date() })
        .strict(),
    z
        .object({ kind: z.literal("cancel"), sub_reason: CancelReasonSchema })
        .strict(),
]);
export function approvalTiers(
    request: z.infer<typeof DeliveryRequestSchema>,
    businessDate: string,
) {
    const p = DeliveryRequestSchema.parse(request);
    if (p.kind === "cancel") return ["spv"] as const;
    const days =
        (Date.parse(p.requested_date + "T00:00:00Z") -
            Date.parse(businessDate + "T00:00:00Z")) /
        86400000;
    if (!Number.isInteger(days) || days < 0)
        throw new Error(
            "Tanggal kirim ulang tidak boleh sebelum tanggal pengiriman.",
        );
    return days < 3 ? (["spv"] as const) : (["spv", "branch_manager"] as const);
}
