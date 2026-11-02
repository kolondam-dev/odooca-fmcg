import { test, expect, checkIn } from "./session-fixture";
import { saveVisitPhoto } from "./visit-helpers";

test("running mode toggle and demo mode geofence/gps bypass", async ({
    page,
}) => {
    // 1. Load app
    await page.goto("./");
    await checkIn(page);
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();

    // 2. Pill button in topbar
    const modePill = page.locator(".running-mode-pill");
    await expect(modePill).toBeVisible();

    const banner = page.locator(".demo-mode-banner");

    // Initially starts in LIVE mode: banner is hidden
    await expect(banner).toHaveCount(0);
    await expect(modePill).toHaveText("LIVE");

    // Click pill to toggle to DEMO mode: banner appears
    await modePill.click();
    await expect(banner).toBeVisible();
    await expect(banner).toHaveText(
        "Aplikasi running pada mode demo, validasi geofence dan timestamp diabaikan",
    );
    await expect(modePill).toHaveText("DEMO");

    // Open visit panel
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();

    // In demo mode, start button should be usable even if far away or no GPS
    const start = page.getByRole("button", {
        name: "Mulai kunjungan",
        exact: true,
    });

    // Save photo
    await saveVisitPhoto(page, "check-in");
    await expect(start).toBeEnabled();

    // Check-in succeeds with simulated fix in DEMO mode
    await start.click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();

    // Switch back to LIVE mode: banner disappears
    await modePill.click();
    await expect(banner).toHaveCount(0);
    await expect(modePill).toHaveText("LIVE");
});
