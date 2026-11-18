export const money = (n: number) =>
    new Intl.NumberFormat("id-ID", {
        style: "currency",
        currency: "IDR",
        maximumFractionDigits: 0,
    }).format(n);
/** Zona kerja DS: WITA. */
export const WORK_TZ = "Asia/Makassar";
/**
 * Jam gaya DS "HH.mm" (24 jam, titik, WITA). Nilai kosong atau tidak valid -> "".
 * Satu-satunya pemformat jam hari; jangan mengandalkan locale peramban.
 */
export function clockHM(value?: string | number | Date | null): string {
    if (value === undefined || value === null || value === "") return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const parts = new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
        timeZone: WORK_TZ,
    }).formatToParts(date);
    const get = (type: string) =>
        parts.find((part) => part.type === type)?.value ?? "";
    return `${get("hour")}.${get("minute")}`;
}
export const time = (value: string) => clockHM(value);
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
