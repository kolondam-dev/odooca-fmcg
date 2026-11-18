import { distanceMeters } from "./format";

/** Titik tujuan layar Navigasi (DS `Navigasi`). Tidak disimpan di riwayat browser. */
export type NavTarget = {
    name: string;
    address: string;
    latitude: number;
    longitude: number;
};
export type NavFix = { latitude: number; longitude: number };

const validCoordinate = (p: NavFix) =>
    Number.isFinite(p.latitude) &&
    Number.isFinite(p.longitude) &&
    Math.abs(p.latitude) <= 90 &&
    Math.abs(p.longitude) <= 180;

const oneDecimal = new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
});
const whole = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });

/** Jarak dalam km gaya DS ("0,1 km"); di bawah 0,1 km ditulis "< 0,1 km". */
export function kmLabel(meters: number): string {
    if (!Number.isFinite(meters) || meters < 0) return "";
    if (meters < 50) return "< 0,1 km";
    const km = meters / 1000;
    return `${km >= 10 ? whole.format(km) : oneDecimal.format(km)} km`;
}

/** Jarak perangkat ke tujuan, selalu dengan keterangan garis lurus. */
export function straightLineLabel(
    target: NavFix,
    fix?: NavFix,
): string | undefined {
    if (!fix || !validCoordinate(target) || !validCoordinate(fix))
        return undefined;
    const label = kmLabel(
        distanceMeters(
            fix.latitude,
            fix.longitude,
            target.latitude,
            target.longitude,
        ),
    );
    return label ? `${label} (garis lurus)` : undefined;
}

export type SchematicMap = {
    width: number;
    height: number;
    target: { x: number; y: number };
    /** Kosong bila posisi perangkat belum ada. */
    user?: { x: number; y: number };
    /** Garis lurus dari perangkat ke tujuan. */
    line?: { length: number; angle: number };
};

/**
 * Skema posisi (bukan peta jalan): kedua titik diproyeksikan datar dan
 * dimuat dalam bidang gambar dengan margin. Utara di atas.
 */
export function schematicMap(
    target: NavFix,
    fix?: NavFix,
    width = 390,
    height = 400,
    margin = 56,
): SchematicMap {
    const centre = { x: width / 2, y: height / 2 };
    if (!fix || !validCoordinate(target) || !validCoordinate(fix))
        return { width, height, target: centre };
    const metresPerDegree = 111_320;
    const dx =
        (target.longitude - fix.longitude) *
        metresPerDegree *
        Math.cos(((target.latitude + fix.latitude) / 2) * (Math.PI / 180));
    const dy = (fix.latitude - target.latitude) * metresPerDegree; // utara = atas
    const span = Math.hypot(dx, dy);
    if (span < 1) return { width, height, target: centre };
    const scale = Math.min(
        (width - 2 * margin) / Math.max(Math.abs(dx), 1e-6),
        (height - 2 * margin) / Math.max(Math.abs(dy), 1e-6),
    );
    const t = {
        x: centre.x + (dx * scale) / 2,
        y: centre.y + (dy * scale) / 2,
    };
    const u = {
        x: centre.x - (dx * scale) / 2,
        y: centre.y - (dy * scale) / 2,
    };
    return {
        width,
        height,
        target: t,
        user: u,
        line: {
            length: Math.hypot(t.x - u.x, t.y - u.y),
            angle: (Math.atan2(t.y - u.y, t.x - u.x) * 180) / Math.PI,
        },
    };
}
