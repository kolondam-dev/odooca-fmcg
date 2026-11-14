import { z } from "zod";

/** Payload `hris.leave.request` yang didukung server saat ini (tanpa jenis cuti, lampiran, atau saldo). */
export const LeaveRequestSchema = z
    .object({
        date_from: z.iso.date(),
        date_to: z.iso.date(),
        reason: z.string().trim().min(3).max(500),
    })
    .strict()
    .refine((p) => p.date_to >= p.date_from, {
        path: ["date_to"],
        message: "Tanggal selesai tidak boleh sebelum mulai.",
    });
export type LeaveRequest = z.infer<typeof LeaveRequestSchema>;

/** Hari kerja (Senin–Jumat) inklusif; hanya tampilan, server tetap menghitung ulang dan memotong saldo. */
export function workingDays(from: string, to: string): number | undefined {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to))
        return undefined;
    const a = Date.parse(`${from}T00:00:00Z`);
    const b = Date.parse(`${to}T00:00:00Z`);
    if (Number.isNaN(a) || Number.isNaN(b) || b < a) return undefined;
    let n = 0;
    for (let t = a; t <= b; t += 86400000) {
        const d = new Date(t).getUTCDay();
        if (d !== 0 && d !== 6) n++;
    }
    return n;
}
