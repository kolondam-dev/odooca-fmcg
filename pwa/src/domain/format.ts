export const money = (n: number) =>
    new Intl.NumberFormat("id-ID", {
        style: "currency",
        currency: "IDR",
        maximumFractionDigits: 0,
    }).format(n);
/** Zona kerja DS: WITA. */
export const WORK_TZ = "Asia/Makassar";
const clockParts = (value?: string | number | Date | null) => {
    if (value === undefined || value === null || value === "") return undefined;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return undefined;
    const parts = new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hourCycle: "h23",
        timeZone: WORK_TZ,
    }).formatToParts(date);
    const get = (type: string) =>
        parts.find((part) => part.type === type)?.value ?? "";
    return { h: get("hour"), m: get("minute"), s: get("second") };
};
/**
 * Jam kejadian gaya DS "HH.mm.ss" (24 jam, titik, WITA). Waktu yang tercatat
 * (absen, order tersimpan, antrean, riwayat) selalu lengkap sampai detik
 * karena dibutuhkan untuk audit. Kosong atau tidak valid -> "".
 */
export function clockHMS(value?: string | number | Date | null): string {
    const c = clockParts(value);
    return c ? `${c.h}.${c.m}.${c.s}` : "";
}
/**
 * Jam rencana tanpa detik ("HH.mm"), khusus slot jadwal (jam kunjungan PJP),
 * BUKAN waktu kejadian. Untuk waktu yang tercatat pakai `clockHMS`.
 */
export function clockHM(value?: string | number | Date | null): string {
    const c = clockParts(value);
    return c ? `${c.h}.${c.m}` : "";
}
export const time = (value: string) => clockHMS(value);
export const queueLabels = {
    queued: "Menunggu koneksi",
    sending: "Mengirim",
    accepted: "Diterima simulator",
    needs_approval: "Menunggu approval",
    rejected: "Perlu tindakan",
    auth_required: "Sesi habis",
};
export function haptic() {
    if (
        !matchMedia("(prefers-reduced-motion: reduce)").matches &&
        "vibrate" in navigator
    )
        navigator.vibrate(12);
}
export function distanceMeters(
    lat1: number,
    lon1: number,
    lat2: number,
    lon2: number,
) {
    const rad = Math.PI / 180;
    const a =
        Math.sin(((lat2 - lat1) * rad) / 2) ** 2 +
        Math.cos(lat1 * rad) *
            Math.cos(lat2 * rad) *
            Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
    return 6371000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
export function geofence(
    distance: number,
    accuracy: number,
    radius: number,
): "inside" | "outside" | "uncertain" {
    if (
        ![distance, accuracy, radius].every(Number.isFinite) ||
        distance < 0 ||
        accuracy < 0 ||
        radius < 5 ||
        radius > 150
    )
        return "uncertain";
    return distance + accuracy <= radius
        ? "inside"
        : distance - accuracy > radius
          ? "outside"
          : "uncertain";
}
