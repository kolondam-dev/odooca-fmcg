export type MapPoint = { latitude: number; longitude: number };
export type MapSite = MapPoint & {
    name: string;
    radius: number;
    simulated?: boolean;
};
export type MapFix = MapPoint & { accuracy: number; simulated?: boolean };
export const validPoint = (p: MapPoint) =>
    Number.isFinite(p.latitude) &&
    Number.isFinite(p.longitude) &&
    Math.abs(p.latitude) <= 85.05112878 &&
    Math.abs(p.longitude) <= 180;
const world = (p: MapPoint, z: number) => {
    const size = 256 * 2 ** z;
    const lat =
        (Math.max(-85.05112878, Math.min(85.05112878, p.latitude)) * Math.PI) /
        180;
    return {
        x: ((p.longitude + 180) / 360) * size,
        y:
            ((1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2) *
            size,
    };
};
export function checkinMap(site: MapSite, fix?: MapFix, zoom?: number) {
    if (
        !validPoint(site) ||
        !Number.isFinite(site.radius) ||
        site.radius <= 0 ||
        (zoom !== undefined && !Number.isFinite(zoom)) ||
        (fix &&
            (!validPoint(fix) ||
                !Number.isFinite(fix.accuracy) ||
                fix.accuracy < 0))
    )
        throw new Error("Koordinat peta tidak valid.");
    const project = (z: number) => {
        const a = world(site, z),
            b = world(fix ?? site, z),
            size = 256 * 2 ** z;
        // Keep nearby points together across the antimeridian.
        b.x = a.x + (((b.x - a.x + size * 1.5) % size) - size / 2);
        const scale = (lat: number) =>
            size /
            (40075016.686 *
                Math.cos((Math.min(85, Math.abs(lat)) * Math.PI) / 180));
        return {
            a,
            b,
            r: site.radius * scale(site.latitude),
            accuracy:
                (fix?.accuracy ?? 0) * scale(fix?.latitude ?? site.latitude),
        };
    };
    let z = 18;
    for (; z > 0; z--) {
        const { a, b, r, accuracy } = project(z);
        if (
            Math.abs(a.x - b.x) + 2 * Math.max(r, accuracy) < 420 &&
            Math.abs(a.y - b.y) + 2 * Math.max(r, accuracy) < 230
        )
            break;
    }
    z = zoom === undefined ? z : Math.max(0, Math.min(19, Math.round(zoom)));
    const { a, b, r, accuracy } = project(z);
    const left = (a.x + b.x) / 2 - 256,
        top = (a.y + b.y) / 2 - 160;
    const tiles = [];
    for (
        let x = Math.floor(left / 256);
        x <= Math.floor((left + 511) / 256);
        x++
    )
        for (
            let y = Math.floor(top / 256);
            y <= Math.floor((top + 319) / 256);
            y++
        ) {
            if (y < 0 || y >= 2 ** z) continue;
            tiles.push({
                key: `${z}/${x}/${y}`,
                url: `https://tile.openstreetmap.org/${z}/${((x % 2 ** z) + 2 ** z) % 2 ** z}/${y}.png`,
                x: x * 256 - left,
                y: y * 256 - top,
            });
        }
    return {
        zoom: z,
        tiles,
        site: { x: a.x - left, y: a.y - top, radius: r },
        fix: { x: b.x - left, y: b.y - top, radius: accuracy },
    };
}
