import { describe, expect, it } from "vitest";
import {
    kmLabel,
    schematicMap,
    straightLineLabel,
} from "../src/domain/navigation-target";

const target = { latitude: 1.4748, longitude: 124.8421 };

describe("kmLabel", () => {
    it("memakai koma desimal dan satu angka di belakang koma", () => {
        expect(kmLabel(100)).toBe("0,1 km");
        expect(kmLabel(1250)).toBe("1,3 km");
        expect(kmLabel(9_949)).toBe("9,9 km");
    });
    it("membulatkan ke km utuh mulai 10 km", () => {
        expect(kmLabel(12_400)).toBe("12 km");
    });
    it("tidak menulis 0,0 km untuk jarak sangat dekat", () => {
        expect(kmLabel(0)).toBe("< 0,1 km");
        expect(kmLabel(49)).toBe("< 0,1 km");
    });
    it("menolak nilai tidak valid", () => {
        expect(kmLabel(Number.NaN)).toBe("");
        expect(kmLabel(-5)).toBe("");
    });
});

describe("straightLineLabel", () => {
    it("selalu memberi keterangan garis lurus", () => {
        // ±111 m ke utara.
        const label = straightLineLabel(
            { latitude: target.latitude + 0.001, longitude: target.longitude },
            target,
        );
        expect(label).toBe("0,1 km (garis lurus)");
    });
    it("kosong tanpa posisi perangkat atau koordinat rusak", () => {
        expect(straightLineLabel(target)).toBeUndefined();
        expect(
            straightLineLabel(target, { latitude: 99, longitude: 0 }),
        ).toBeUndefined();
        expect(
            straightLineLabel({ latitude: Number.NaN, longitude: 0 }, target),
        ).toBeUndefined();
    });
});

describe("schematicMap", () => {
    it("menaruh tujuan di tengah bila posisi perangkat belum ada", () => {
        const m = schematicMap(target);
        expect(m.target).toEqual({ x: m.width / 2, y: m.height / 2 });
        expect(m.user).toBeUndefined();
        expect(m.line).toBeUndefined();
    });
    it("utara di atas: tujuan di utara perangkat berada lebih atas", () => {
        const m = schematicMap(
            { latitude: target.latitude + 0.002, longitude: target.longitude },
            target,
        );
        expect(m.user && m.target.y < m.user.y).toBe(true);
        expect(m.user && Math.abs(m.target.x - m.user.x)).toBeLessThan(1);
    });
    it("timur di kanan: tujuan di timur perangkat berada lebih kanan", () => {
        const m = schematicMap(
            { latitude: target.latitude, longitude: target.longitude + 0.002 },
            target,
        );
        expect(m.user && m.target.x > m.user.x).toBe(true);
        expect(m.user && Math.abs(m.target.y - m.user.y)).toBeLessThan(1);
    });
    it("kedua titik selalu berada di dalam bidang gambar dengan margin", () => {
        for (const [dLat, dLon] of [
            [0.0001, 0.0001],
            [0.05, -0.002],
            [-0.3, 0.4],
        ]) {
            const m = schematicMap(
                {
                    latitude: target.latitude + dLat,
                    longitude: target.longitude + dLon,
                },
                target,
            );
            for (const p of [m.target, m.user!]) {
                expect(p.x).toBeGreaterThanOrEqual(56 - 1e-6);
                expect(p.x).toBeLessThanOrEqual(m.width - 56 + 1e-6);
                expect(p.y).toBeGreaterThanOrEqual(56 - 1e-6);
                expect(p.y).toBeLessThanOrEqual(m.height - 56 + 1e-6);
            }
        }
    });
    it("titik yang berimpit tidak menghasilkan garis atau NaN", () => {
        const m = schematicMap(target, target);
        expect(m.user).toBeUndefined();
        expect(Number.isFinite(m.target.x)).toBe(true);
    });
});
