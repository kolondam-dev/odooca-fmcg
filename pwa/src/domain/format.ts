export const money = (n: number) =>
    new Intl.NumberFormat("id-ID", {
        style: "currency",
        currency: "IDR",
        maximumFractionDigits: 0,
    }).format(n);
export const time = (value: string) =>
    new Date(value).toLocaleTimeString("id-ID", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Makassar",
    });
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
export function geofence(distance: number, accuracy: number, radius: number) {
    if (
        ![distance, accuracy, radius].every(Number.isFinite) ||
        distance < 0 ||
        accuracy < 0 ||
        radius < 5 ||
        radius > 15
    )
        return "uncertain";
    return distance + accuracy <= radius
        ? "inside"
        : distance - accuracy > radius
          ? "outside"
          : "uncertain";
}
