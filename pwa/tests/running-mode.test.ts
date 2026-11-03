import { assertVisitEvidence } from "../src/domain/visit-evidence";
import { type VisitContext } from "../src/domain/visit-contracts";
import { SalesVisits } from "../src/domain/visits";
import { FieldStore } from "../src/storage/store";
import { Outbox } from "../src/domain/outbox";
import { MockProvider } from "../src/data/mock";
import {
    MorningSimulation,
    MORNING_KEY,
    MORNING_HISTORY_PREFIX,
    morningReady,
} from "../src/domain/morning";
import { ownerKey } from "../src/domain/contracts";
import { makeVisitPhoto } from "./visit-fixtures";
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

describe("Running Mode Gate (DEMO | LIVE)", () => {
    it.each([
        [true, "live"],
        [false, "live"],
        [true, "demo"],
        [false, "demo"],
    ] as const)(
        "rolls a DEMO day forward (closed=%s, nextMode=%s) without losing history or pending commands",
        async (closed, nextMode) => {
            vi.useFakeTimers({ toFake: ["Date"] });
            vi.setSystemTime(new Date("2026-10-27T00:00:00Z"));
            vi.stubGlobal("navigator", { onLine: true });
            const testStore = new FieldStore(crypto.randomUUID());
            try {
                setRunningMode("demo");
                const provider = new MockProvider("sales");
                const identity = await provider.bootstrap();
                const owner = ownerKey(identity);
                const service = new MorningSimulation(
                    testStore,
                    identity,
                    provider,
                );
                const first = await service.openDay();
                if (closed) await service.clockOut();
                const prior = await testStore.draft(owner, MORNING_KEY);
                const engine = new Outbox(testStore, owner, provider);
                await engine.enqueue(
                    "hris.leave.request",
                    { reason: "Pending day one" },
                    "Pending day one",
                );
                const pending = await testStore.list(owner);
                expect(pending).toHaveLength(1);

                vi.setSystemTime(new Date("2026-10-27T16:00:01Z"));
                setRunningMode(nextMode);
                expect(await service.restore()).toBeUndefined();
                expect(morningReady(first, owner)).toBe(false);
                const next = await service.openDay();
                expect(next.businessDate).toBe("2026-10-28");
                expect(next.clockOutAt).toBeUndefined();
                expect(next.sessionId).not.toBe(first.sessionId);
                expect(morningReady(next, owner)).toBe(true);
                expect(
                    await testStore.draft(
                        owner,
                        `${MORNING_HISTORY_PREFIX}2026-10-27:${first.sessionId}`,
                    ),
                ).toEqual(prior);
                expect(await testStore.list(owner)).toEqual(pending);
            } finally {
                await testStore.close();
                vi.useRealTimers();
                vi.unstubAllGlobals();
            }
        },
    );

    it.each([9_999, 10_001])(
        "LIVE snapshot future skew boundary: %s ms",
        async (ahead) => {
            vi.useFakeTimers({ toFake: ["Date"] });
            vi.setSystemTime(new Date("2026-10-27T00:00:00Z"));
            vi.stubGlobal("navigator", { onLine: true });
            setRunningMode("live");
            const testStore = new FieldStore(crypto.randomUUID());
            try {
                const provider = new MockProvider("sales");
                const identity = await provider.bootstrap();
                const service = new MorningSimulation(
                    testStore,
                    identity,
                    provider,
                );
                await service.acceptAttendance();
                const snapshot = await provider.snapshot();
                vi.spyOn(provider, "snapshot").mockResolvedValueOnce({
                    ...snapshot,
                    updatedAt: new Date(Date.now() + ahead).toISOString(),
                });
                if (ahead <= 10_000) {
                    expect(
                        morningReady(await service.open(), ownerKey(identity)),
                    ).toBe(true);
                } else {
                    await expect(service.open()).rejects.toThrow(
                        "belum lengkap",
                    );
                    expect(
                        morningReady(
                            await service.restore(),
                            ownerKey(identity),
                        ),
                    ).toBe(false);
                }
            } finally {
                await testStore.close();
                vi.useRealTimers();
                vi.unstubAllGlobals();
            }
        },
    );
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

    it("respects demo_unrestricted provenance during DEMO -> LIVE mode switch (supervisor counterexample probe)", async () => {
        const now = Date.now();
        const capturedAt = new Date(now).toISOString();

        // 1. context.site is normal WITHOUT demo_unrestricted flag (as when synced in LIVE)
        const context: VisitContext = {
            visit_uuid: crypto.randomUUID(),
            work_session_id: crypto.randomUUID(),
            business_date: "2026-10-27",
            snapshot_version: "v1",
            outlet_id: "outlet-1",
            site: {
                latitude: 1.48,
                longitude: 124.84,
                radius: 100, // 100m radius
            },
            fix: {
                latitude: 1.49, // ~1.1 km away (outside geofence)
                longitude: 124.84,
                accuracy: 5,
                sampled_at: capturedAt,
            },
        };

        const ref: EvidenceReference = {
            id: crypto.randomUUID(),
            latitude: 1.49, // 1.1 km outside
            longitude: 124.84,
            accuracy: 5,
            capturedAt,
        };

        const blob = new Blob(["test-photo"], { type: "image/jpeg" });
        const map = new Blob(["test-map"], { type: "image/png" });
        const photoSha256 = await sha256(blob);
        const mapSha256 = await sha256(map);

        const visual = {
            version: 1 as const,
            kind: "simulation_grid" as const,
            demo_unrestricted: true as const, // Created in DEMO mode
            selectedAt: capturedAt,
            fixSampledAt: capturedAt,
            photoSha256,
            mapSha256,
        };

        const dummyRow = {
            key: `sales:${ref.id}`,
            owner: "sales",
            blob,
            ...ref,
            mapStatus: "pending" as const,
        };

        const bindingSha256 = await sha256(evidenceBinding(dummyRow, visual));
        ref.packageHash = bindingSha256;

        const row: Evidence = {
            ...dummyRow,
            visual: { ...visual, bindingSha256, map },
        };

        const mockStore = {
            getEvidence: async (_owner: string, _id: string) => row,
        } as unknown as FieldStore;

        // In DEMO mode: assertVisitEvidence succeeds
        setRunningMode("demo");
        await expect(
            assertVisitEvidence(ref, context, capturedAt, "sales", mockStore),
        ).resolves.toBeUndefined();

        // Switch to LIVE mode: assertVisitEvidence MUST STILL SUCCEED for valid DEMO history!
        setRunningMode("live");
        await expect(
            assertVisitEvidence(ref, context, capturedAt, "sales", mockStore),
        ).resolves.toBeUndefined();

        // Counterexample check: if the package was NOT demo_unrestricted, LIVE mode MUST reject out-of-geofence fix!
        const strictVisual = {
            version: 1 as const,
            kind: "simulation_grid" as const,
            selectedAt: capturedAt,
            fixSampledAt: capturedAt,
            photoSha256,
            mapSha256,
        };
        const strictBinding = await sha256(
            evidenceBinding(dummyRow, strictVisual),
        );
        const strictRef: EvidenceReference = {
            ...ref,
            packageHash: strictBinding,
        };
        const strictRow: Evidence = {
            ...dummyRow,
            visual: { ...strictVisual, bindingSha256: strictBinding, map },
        };
        const strictStore = {
            getEvidence: async (_owner: string, _id: string) => strictRow,
        } as unknown as FieldStore;

        await expect(
            assertVisitEvidence(
                strictRef,
                context,
                capturedAt,
                "sales",
                strictStore,
            ),
        ).rejects.toThrow("Lokasi berada di luar geofence outlet.");
    });

    it("restores visits created in DEMO after switching to LIVE without locking workspace or allowing new invalid LIVE actions", async () => {
        vi.useFakeTimers({ toFake: ["Date"] });
        vi.setSystemTime(new Date("2026-10-27T08:00:00Z"));
        vi.stubGlobal("navigator", { onLine: true });

        const storeName = crypto.randomUUID();
        const testStore = new FieldStore(storeName);

        try {
            const provider = new MockProvider("sales");
            const identity = await provider.bootstrap();
            const owner = ownerKey(identity);
            const engine = new Outbox(testStore, owner, provider);
            const morning = new MorningSimulation(
                testStore,
                identity,
                provider,
            );

            await morning.acceptAttendance();
            const morningState = await morning.open();
            const outlet = morningState.snapshot!.outlets[0];

            const visitsService = new SalesVisits(
                testStore,
                identity,
                provider,
                engine,
            );

            // 1. User is in DEMO mode: creates visit with fix outside radius (e.g. +0.01 lat ~1.1 km)
            setRunningMode("demo");
            const farFix: VisitFix = {
                latitude: outlet.latitude + 0.01,
                longitude: outlet.longitude,
                accuracy: 3,
                sampled_at: new Date().toISOString(),
            };

            const inPhoto = await makeVisitPhoto(
                testStore,
                owner,
                farFix,
                true,
            );
            await visitsService.checkIn(outlet.id, farFix, inPhoto);

            const outPhoto = await makeVisitPhoto(
                testStore,
                owner,
                farFix,
                true,
            );
            await visitsService.checkOut(
                outlet.id,
                farFix,
                "no_order",
                "Outlet visited in demo mode",
                outPhoto,
            );

            // 2. Switch mode to LIVE
            setRunningMode("live");

            // 3. Restore and validate media in LIVE mode: must succeed and not lock workspace!
            const restored = await visitsService.restore(outlet.id);
            expect(restored.history.length).toBe(1);
            expect(restored.history[0].check_out).not.toBeNull();

            // 4. In LIVE mode, attempting a NEW visit with out-of-geofence fix is strictly rejected!
            const anotherOutlet = morningState.snapshot!.outlets[1];
            const livePhoto = await makeVisitPhoto(
                testStore,
                owner,
                farFix,
                false,
            );
            await expect(
                visitsService.checkIn(anotherOutlet.id, farFix, livePhoto),
            ).rejects.toThrow("Lokasi berada di luar geofence outlet.");
        } finally {
            await testStore.close();
            vi.useRealTimers();
            vi.unstubAllGlobals();
        }
    });

    it("preserves DEMO morning session provenance across DEMO to LIVE mode switch and tolerates network skew", async () => {
        vi.stubGlobal("navigator", { onLine: true });
        const testStore = new FieldStore();
        try {
            // 1. In DEMO mode, accept attendance and open morning session
            setRunningMode("demo");
            expect(isDemoMode()).toBe(true);

            const provider = new MockProvider("sales");
            const identity = await provider.bootstrap();
            const service = new MorningSimulation(
                testStore,
                identity,
                provider,
            );

            await service.acceptAttendance();
            const session = await service.open();
            expect(session.demo_unrestricted).toBe(true);
            expect(session.sessionId).toBeTruthy();

            // 2. Switch mode to LIVE
            setRunningMode("live");
            expect(isDemoMode()).toBe(false);

            // 3. Restore in LIVE mode: must succeed and remain ready
            const restored = await service.restore();
            expect(restored).toBeDefined();
            expect(restored?.sessionId).toBe(session.sessionId);
            expect(restored?.demo_unrestricted).toBe(true);

            // 4. Test network skew tolerance (e.g. 2 seconds server timestamp ahead of client openedAt)
            const skewedSnapshot = {
                ...session.snapshot!,
                updatedAt: new Date(
                    Date.parse(session.openedAt!) + 2000,
                ).toISOString(),
            };
            const skewedRecord = {
                ...session,
                snapshot: skewedSnapshot,
                demo_unrestricted: undefined, // strictly LIVE record
            };
            await testStore.draft(
                ownerKey(identity),
                "morning-session-v1",
                skewedRecord,
            );
            const restoredLive = await service.restore();
            expect(restoredLive).toBeDefined();
            expect(restoredLive?.sessionId).toBe(session.sessionId);
        } finally {
            await testStore.close();
            vi.unstubAllGlobals();
        }
    });
});
