import { describe, expect, it, beforeEach, vi } from "vitest";
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
import { captureVisitLocation } from "../src/domain/visits";
import {
    validateEvidenceTime,
    assertLocalEvidence,
    evidenceBinding,
    sha256,
    type EvidenceReference,
} from "../src/domain/evidence-package";
import type { Evidence } from "../src/storage/store";
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
        vi.restoreAllMocks();
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

    it("in demo mode, captureVisitLocation provides simulated fallback when GPS is denied or unavailable", async () => {
        setRunningMode("demo");

        // Simulate permission denied error
        let sourceVal = "";
        const mockGeoDenied = {
            getCurrentPosition: (
                _success: unknown,
                error: (e: { code: number }) => void,
            ) => {
                error({ code: 1 });
            },
        };
        // @ts-ignore
        vi.stubGlobal("navigator", { geolocation: mockGeoDenied });

        const fix = await captureVisitLocation((src) => {
            sourceVal = src;
        });

        expect(sourceVal).toBe("demo");
        expect(fix.latitude).toBe(1.465);
        expect(fix.longitude).toBe(124.833);
        expect(fix.accuracy).toBe(1);

        // Simulate missing navigator.geolocation
        // @ts-ignore
        vi.stubGlobal("navigator", { geolocation: undefined });
        sourceVal = "";
        const fixNoGeo = await captureVisitLocation((src) => {
            sourceVal = src;
        });
        expect(sourceVal).toBe("demo");
        expect(fixNoGeo.latitude).toBe(1.465);
    });

    it("in live mode, captureVisitLocation rejects GPS failure", async () => {
        setRunningMode("live");

        const mockGeoDenied = {
            getCurrentPosition: (
                _success: unknown,
                error: (e: { code: number }) => void,
            ) => {
                error({ code: 1 });
            },
        };
        // @ts-ignore
        vi.stubGlobal("navigator", { geolocation: mockGeoDenied });

        await expect(captureVisitLocation()).rejects.toThrow(
            "Izin lokasi ditolak. Aktifkan izin lokasi untuk kunjungan.",
        );

        // @ts-ignore
        vi.stubGlobal("navigator", { geolocation: undefined });
        await expect(captureVisitLocation()).rejects.toThrow(
            "Geolocation tidak tersedia pada perangkat ini.",
        );
    });

    it("validates evidence time according to running mode and demo_unrestricted history", async () => {
        const now = Date.now();
        const ref: EvidenceReference = {
            id: crypto.randomUUID(),
            latitude: 1.465,
            longitude: 124.833,
            accuracy: 3,
            capturedAt: new Date(now).toISOString(),
        };

        // 2 hours ago
        const staleSelectedAt = new Date(now - 7200000).toISOString();
        const staleFixAt = new Date(now - 7200000).toISOString();

        // 1. In LIVE mode without relaxed: throws
        setRunningMode("live");
        expect(() =>
            validateEvidenceTime(ref, staleSelectedAt, staleFixAt, false),
        ).toThrow(
            "Waktu/akurasi bukti tidak valid. Ambil ulang foto dan lokasi.",
        );

        // 2. In DEMO mode: accepts stale times
        setRunningMode("demo");
        expect(() =>
            validateEvidenceTime(ref, staleSelectedAt, staleFixAt, true),
        ).not.toThrow();

        // 3. Restoring DEMO package in LIVE mode: succeeds without locking workspace
        setRunningMode("live");
        const owner = "sales";
        const row: Evidence = {
            key: `${owner}:${ref.id}`,
            owner,
            blob: new Blob(["photo"], { type: "image/jpeg" }),
            ...ref,
            mapStatus: "pending",
        };
        const map = new Blob(["pinpoint"], { type: "image/png" });
        const visual = {
            version: 1 as const,
            kind: "simulation_grid" as const,
            demo_unrestricted: true as const,
            selectedAt: staleSelectedAt,
            fixSampledAt: staleFixAt,
            photoSha256: await sha256(row.blob),
            mapSha256: await sha256(map),
        };
        const bindingSha256 = await sha256(evidenceBinding(row, visual));
        row.visual = { ...visual, bindingSha256, map };
        ref.packageHash = bindingSha256;

        // Even though current mode is LIVE and timestamps are 2 hours old,
        // visual.demo_unrestricted allows restore to succeed!
        await expect(
            assertLocalEvidence(row, ref, owner),
        ).resolves.toBeUndefined();
    });
});
