import { test as base, expect, type Page } from "@playwright/test";
import { MockProvider } from "../../src/data/mock";
import "fake-indexeddb/auto";
(globalThis as Record<string, unknown>).__DEMO__ = true;
const actors = new WeakMap<Page, string>();
const legacyServers = new WeakSet<Page>();
/** Simulasikan server tanpa kapabilitas baru (`features` tidak dikirim) pada halaman ini. */
export function useLegacyServer(page: Page) {
    legacyServers.add(page);
}
export async function changeTestAccount(page: Page, actor: string) {
    actors.set(page, actor);
    if (await page.evaluate(() => navigator.onLine))
        await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    else await page.reload();
}
// HTTP fixtures emulate authenticated backend responses, never a runtime login bypass.
export const test = base.extend({
    page: async ({ page }, use) => {
        actors.set(page, "sales");
        const install = page.clock.install.bind(page.clock);
        page.clock.install = async (options) => {
            await page.addInitScript(() => {
                (
                    window as unknown as { __noDateShift?: boolean }
                ).__noDateShift = true;
            });
            await install(options);
        };
        await page.addInitScript(() => {
            const RealDate = window.Date;
            const witaDateStr = new RealDate().toLocaleDateString("en-CA", {
                timeZone: "Asia/Makassar",
            });
            const parts = witaDateStr.split("-").map(Number);
            const witaDay = new RealDate(
                Date.UTC(parts[0], parts[1] - 1, parts[2], 12, 0, 0),
            ).getUTCDay();
            const shiftMs = witaDay === 0 ? -3 * 24 * 60 * 60 * 1000 : 0;
            // Tes yang memasang page.clock memakai jam sendiri; pergeseran hari
            // Minggu tidak boleh ikut, atau jam berjalan mundur setelah reload.
            const shift = () =>
                (window as unknown as { __noDateShift?: boolean }).__noDateShift
                    ? 0
                    : shiftMs;
            if (shiftMs !== 0) {
                class ShiftedDate extends RealDate {
                    constructor(...args: unknown[]) {
                        if (args.length === 0) {
                            super(RealDate.now() + shift());
                        } else if (args.length === 1) {
                            super(args[0] as string | number | Date);
                        } else {
                            super(...(args as [number, number, ...number[]]));
                        }
                    }
                    static now() {
                        return RealDate.now() + shift();
                    }
                }
                ShiftedDate.UTC = RealDate.UTC;
                ShiftedDate.parse = RealDate.parse;
                // @ts-expect-error Assign shifted date constructor
                window.Date = ShiftedDate;
            }

            // Sync geolocation timestamp directly with window.Date.now()
            if (navigator.geolocation) {
                const origGet = navigator.geolocation.getCurrentPosition.bind(
                    navigator.geolocation,
                );
                navigator.geolocation.getCurrentPosition = function (
                    success,
                    error,
                    options,
                ) {
                    origGet(
                        function (pos) {
                            try {
                                Object.defineProperty(pos, "timestamp", {
                                    value: window.Date.now(),
                                    configurable: true,
                                    writable: true,
                                });
                            } catch {
                                // Ignore definition error and proceed
                            }
                            success(pos);
                        },
                        error,
                        options,
                    );
                };

                const origWatch = navigator.geolocation.watchPosition.bind(
                    navigator.geolocation,
                );
                navigator.geolocation.watchPosition = function (
                    success,
                    error,
                    options,
                ) {
                    return origWatch(
                        function (pos) {
                            try {
                                Object.defineProperty(pos, "timestamp", {
                                    value: window.Date.now(),
                                    configurable: true,
                                    writable: true,
                                });
                            } catch {
                                // Ignore definition error and proceed
                            }
                            success(pos);
                        },
                        error,
                        options,
                    );
                };
            }
        });
        await page.context().setGeolocation({
            latitude: 1.465,
            longitude: 124.833,
            accuracy: 3,
        });
        await page.route("**/api/v1/me/bootstrap", async (route) => {
            if (new URL(route.request().url()).port !== "4173")
                return route.fallback();
            const provider = new MockProvider(
                actors.get(page) ?? "sales",
                true,
            );
            const identity = await provider.bootstrap();
            const date = await evalRetry(page, () =>
                new Date().toLocaleDateString("en-CA", {
                    timeZone: "Asia/Makassar",
                }),
            );
            await route.fulfill({
                json: {
                    ...identity,
                    businessDate: date,
                    companyName: "PT. Demo FMCG",
                    csrfToken: "fixture-command-csrf",
                },
            });
        });
        await page.route("**/api/v1/sync/snapshot", async (route) => {
            if (new URL(route.request().url()).port !== "4173")
                return route.fallback();
            const provider = new MockProvider(
                actors.get(page) ?? "sales",
                true,
            );
            const snapshot = await provider.snapshot();
            const now = await evalRetry(page, () => new Date().toISOString());
            const date = await evalRetry(page, () =>
                new Date().toLocaleDateString("en-CA", {
                    timeZone: "Asia/Makassar",
                }),
            );
            await route.fulfill({
                json: {
                    ...snapshot,
                    ...(legacyServers.has(page) ? { features: undefined } : {}),
                    updatedAt: now,
                    scope: { ...snapshot.scope, business_date: date },
                    office: {
                        id: "1",
                        name: "Kantor Pusat",
                        latitude: 1.465,
                        longitude: 124.833,
                        radius: 15,
                        coordinate_status: "test",
                    },
                },
            });
        });
        await page.route("**/api/v1/sync/commands", async (route) => {
            if (new URL(route.request().url()).port !== "4173")
                return route.fallback();
            if (
                route.request().headers()["x-csrf-token"] !==
                "fixture-command-csrf"
            ) {
                return route.fulfill({
                    status: 403,
                    body: "Missing fixture CSRF token",
                });
            }
            // Approval simulation belongs to this HTTP fixture, never the live provider.
            const body = route.request().postDataJSON();
            const simulator = new MockProvider(
                actors.get(page) ?? "sales",
                true,
            );
            Object.defineProperty(globalThis, "navigator", {
                configurable: true,
                value: { onLine: true },
            });
            const receipt = await simulator.submit(body);
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                json: receipt,
            });
        });
        await use(page);
    },
});
export { expect };
// page.evaluate dapat gagal bila halaman sedang navigasi; ulangi singkat.
async function evalRetry<T>(page: Page, fn: () => T): Promise<T> {
    for (let i = 0; ; i++) {
        try {
            return await page.evaluate(fn);
        } catch (error) {
            if (i >= 4) throw error;
            await page.waitForTimeout(150);
        }
    }
}
export type { Page, Locator, BrowserContext } from "@playwright/test";
export async function checkIn(page: Page) {
    const clock = page.locator('[data-testid="attendance-record"]');
    if (await clock.isVisible()) return;
    await page.context().grantPermissions(["geolocation"]);
    await page
        .getByRole("button", { name: "Absen masuk", exact: true })
        .first()
        .click();
    await page
        .getByRole("button", { name: "Perbarui lokasi", exact: true })
        .click();
    await expect(
        page.getByRole("region", { name: "Lokasi dan foto absensi" }),
    ).toHaveAttribute("aria-busy", "false");
    await page
        .getByLabel("Alamat / nama lokasi")
        .fill("Jl. Sam Ratulangi, Sario, Manado, Sulawesi Utara");
    await page
        .getByRole("button", { name: "Ambil selfie", exact: true })
        .click();
    await page
        .getByLabel("Buka Kamera Perangkat")
        .setInputFiles("public/icon-192.png");
    await page
        .getByRole("button", { name: "Gunakan foto", exact: true })
        .click();
    await expect(
        page.getByAltText("Foto absensi dengan watermark"),
    ).toBeVisible();
    await page
        .getByRole("region", { name: "Absensi foto dan lokasi" })
        .getByRole("button", { name: "Absen masuk", exact: true })
        .click();
    await expect(clock).toBeVisible();
}

/**
 * Metadata snapshot yang selaras dengan jam peramban fixture: hari Minggu WITA
 * digeser -3 hari (lihat addInitScript di atas), sehingga tes yang mengganti
 * snapshot harus memakai tanggal bisnis yang sama dengan bootstrap fixture.
 */
export function freshSnapshotMeta() {
    const wita = (ms: number) =>
        new Date(ms).toLocaleDateString("en-CA", { timeZone: "Asia/Makassar" });
    const real = Date.now();
    const [y, m, d] = wita(real).split("-").map(Number);
    const shift =
        new Date(Date.UTC(y, m - 1, d, 12)).getUTCDay() === 0
            ? -3 * 24 * 60 * 60 * 1000
            : 0;
    return {
        updatedAt: new Date(real + shift).toISOString(),
        businessDate: wita(real + shift),
    };
}
