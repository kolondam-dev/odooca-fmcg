import { describe, expect, it } from "vitest";
import { checkinMap } from "../src/domain/checkin-map";
const site = {
    name: "Kantor",
    latitude: 1.465,
    longitude: 124.833,
    radius: 15,
};
describe("check-in map projection", () => {
    it("places a coincident fix at center with proportional uncertainty", () => {
        const m = checkinMap(site, { ...site, accuracy: 3 });
        expect(m.site.x).toBeCloseTo(256);
        expect(m.site.y).toBeCloseTo(160);
        expect(m.fix.x).toBeCloseTo(m.site.x);
        expect(m.site.radius / m.fix.radius).toBeCloseTo(5);
        expect(m.tiles.length).toBeLessThanOrEqual(9);
    });
    it("fits distant remote points instead of showing a false nearby fix", () => {
        const m = checkinMap(site, {
            latitude: -6.2,
            longitude: 106.8,
            accuracy: 200,
        });
        expect(m.zoom).toBeLessThan(8);
        for (const p of [m.site, m.fix]) {
            expect(p.x).toBeGreaterThan(0);
            expect(p.x).toBeLessThan(512);
            expect(p.y).toBeGreaterThan(0);
            expect(p.y).toBeLessThan(320);
        }
    });
    it("wraps the date line and only emits valid HTTPS viewport tiles", () => {
        const m = checkinMap(
            { ...site, longitude: 179.999 },
            { latitude: site.latitude, longitude: -179.999, accuracy: 5 },
        );
        expect(m.zoom).toBeGreaterThan(12);
        for (const t of m.tiles) {
            const u = new URL(t.url),
                [z, x, y] = u.pathname
                    .slice(1)
                    .replace(".png", "")
                    .split("/")
                    .map(Number);
            expect(u.origin).toBe("https://tile.openstreetmap.org");
            expect(x).toBeGreaterThanOrEqual(0);
            expect(x).toBeLessThan(2 ** z);
            expect(y).toBeGreaterThanOrEqual(0);
            expect(y).toBeLessThan(2 ** z);
        }
    });
    it.each([NaN, Infinity, -1])("rejects invalid accuracy %s", (accuracy) => {
        expect(() => checkinMap(site, { ...site, accuracy })).toThrow();
    });
    it("rejects invalid anchors and bounds zoom controls", () => {
        expect(() => checkinMap({ ...site, latitude: 91 })).toThrow();
        expect(() => checkinMap({ ...site, radius: 0 })).toThrow();
        expect(checkinMap(site, undefined, 200).zoom).toBe(19);
        expect(checkinMap(site, undefined, -2).zoom).toBe(0);
    });
});
