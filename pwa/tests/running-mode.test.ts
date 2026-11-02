import { describe, expect, it, beforeEach } from "vitest";
import {
    getRunningMode,
    setRunningMode,
    isDemoMode,
    DEMO_BANNER_TEXT,
} from "../src/domain/running-mode";
import {
    requireVisitFix,
    assessVisitFix,
} from "../src/domain/visit-validation";
import {
    type VisitFix,
    type VisitSiteSchema,
} from "../src/domain/visit-contracts";
import type { z } from "zod";

type VisitSite = z.infer<typeof VisitSiteSchema>;

const storeMap = new Map<string, string>();
const mockStorage = {
    getItem: (k: string) => storeMap.get(k) ?? null,
    setItem: (k: string, v: string) => storeMap.set(k, v),
    removeItem: (k: string) => storeMap.delete(k),
    clear: () => storeMap.clear(),
    get length() {
        return storeMap.size;
    },
    key: (i: number) => Array.from(storeMap.keys())[i] ?? null,
};

// Polyfill for node test environment
// @ts-ignore
globalThis.localStorage = mockStorage as unknown as Storage;
// @ts-ignore
globalThis.window = {
    localStorage: mockStorage as unknown as Storage,
    dispatchEvent: () => true,
    addEventListener: () => {},
    removeEventListener: () => {},
} as unknown as Window & typeof globalThis;

// @ts-ignore
if (typeof globalThis.__DEMO__ === "undefined") {
    // @ts-ignore
    globalThis.__DEMO__ = false;
}

describe("Running Mode Gate (DEMO | LIVE)", () => {
    beforeEach(() => {
        storeMap.clear();
    });

    it("defaults to live mode when unconfigured", () => {
        expect(getRunningMode()).toBe("live");
        expect(isDemoMode()).toBe(false);
    });

    it("persists and emits mode switches between DEMO and LIVE", () => {
        setRunningMode("demo");
        expect(getRunningMode()).toBe("demo");
        expect(isDemoMode()).toBe(true);

        setRunningMode("live");
        expect(getRunningMode()).toBe("live");
        expect(isDemoMode()).toBe(false);
    });

    it("has the exact banner text requested by owner", () => {
        expect(DEMO_BANNER_TEXT).toBe(
            "Aplikasi running pada mode demo, validasi geofence dan timestamp diabaikan",
        );
    });

    it("in live mode, rejects out-of-geofence and stale location fixes", () => {
        setRunningMode("live");

        const site: VisitSite = {
            latitude: 1.48,
            longitude: 124.84,
            radius: 100,
        };

        // Fix far outside (e.g. Jakarta coords vs Manado site)
        const farFix: VisitFix = {
            latitude: -6.2,
            longitude: 106.8,
            accuracy: 10,
            sampled_at: new Date().toISOString(),
        };

        expect(() => requireVisitFix(farFix, site)).toThrow(
            "Lokasi berada di luar geofence outlet.",
        );

        // Stale fix (>60s)
        const staleFix: VisitFix = {
            latitude: 1.48,
            longitude: 124.84,
            accuracy: 10,
            sampled_at: new Date(Date.now() - 120000).toISOString(),
        };

        expect(() => requireVisitFix(staleFix, site)).toThrow(
            "Lokasi kedaluwarsa. Ambil lokasi baru.",
        );
    });

    it("in demo mode, ignores geofence and timestamp validation (accepts input from anywhere)", () => {
        setRunningMode("demo");

        const site: VisitSite = {
            latitude: 1.48,
            longitude: 124.84,
            radius: 100,
        };

        // Far outside geofence (e.g. 2000 km away)
        const farFix: VisitFix = {
            latitude: -6.2,
            longitude: 106.8,
            accuracy: 50,
            sampled_at: new Date().toISOString(),
        };

        // Must NOT throw in demo mode
        expect(() => requireVisitFix(farFix, site)).not.toThrow();

        // Stale fix (2 hours ago)
        const staleFix: VisitFix = {
            latitude: 0,
            longitude: 0,
            accuracy: 100,
            sampled_at: new Date(Date.now() - 7200000).toISOString(),
        };

        // Must NOT throw in demo mode
        expect(() => requireVisitFix(staleFix, site)).not.toThrow();

        const assessment = assessVisitFix(staleFix, site);
        // Stale flag is bypassed in demo mode
        expect(assessment.status).not.toBe("stale");
    });
});
