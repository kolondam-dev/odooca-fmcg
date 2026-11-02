import { test, expect, checkIn } from "./session-fixture";
import { saveVisitPhoto } from "./visit-helpers";

test("running mode toggle, demo mode geofence bypass, and preservation on switch to live", async ({
    page,
}) => {
    // 1. Load app and perform morning check-in (starts in LIVE mode)
    await page.goto("./");
    await checkIn(page);
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();

    // 2. Pill button in topbar
    const modePill = page.locator(".running-mode-pill");
    await expect(modePill).toBeVisible();

    const banner = page.locator(".demo-running-banner");

    // Initially starts in LIVE mode: banner is hidden
    await expect(banner).toHaveCount(0);
    await expect(modePill).toHaveText("LIVE");

    // 3. Click pill to toggle to DEMO mode: banner appears
    await modePill.click();
    await expect(banner).toBeVisible();
    await expect(banner).toHaveText(
        "Aplikasi running pada mode demo, validasi geofence dan timestamp diabaikan",
    );
    await expect(modePill).toHaveText("DEMO");

    // 4. Open visit panel
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();

    // In demo mode, start button should be usable even if far away or no GPS
    const start = page.getByRole("button", {
        name: "Mulai kunjungan",
        exact: true,
    });

    // Save photo and check in
    await saveVisitPhoto(page, "check-in");
    await expect(start).toBeEnabled();

    // Check-in succeeds with simulated fix in DEMO mode
    await start.click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();

    // 5. Checkout the visit while still in DEMO mode
    await saveVisitPhoto(page, "check-out");
    await page
        .getByLabel("Catatan kunjungan")
        .fill("Kunjungan selesai dalam mode demo");
    await page.getByLabel("Hasil kunjungan").selectOption("outlet_closed");
    await page
        .getByRole("button", { name: "Tutup kunjungan", exact: true })
        .click();
    await expect(
        page.getByText("Kunjungan ditutup lokal", { exact: false }),
    ).toBeVisible();

    // 6. Switch back to LIVE mode: banner disappears
    await modePill.click();
    await expect(banner).toHaveCount(0);
    await expect(modePill).toHaveText("LIVE");

    // 7. Navigate out, reload page in LIVE mode
    await page.getByRole("button", { name: "Beranda", exact: true }).click();
    await page.reload();
    await expect(page.getByText("Sesi aktif", { exact: true })).toBeVisible();

    // 8. Re-open Toko Sinar Pagi in LIVE mode: history is preserved, workspace is not locked!
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await expect(
        page.getByText("Kunjungan ditutup lokal", { exact: false }),
    ).toBeVisible();

    // 9. Navigate to a new unvisited outlet in LIVE mode: out-of-radius fix is strictly guarded
    await page.getByRole("button", { name: "Beranda", exact: true }).click();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Berkat Bahu/ }).click();

    // In LIVE mode without valid in-geofence GPS, starting a new visit is disabled
    const liveStart = page.getByRole("button", {
        name: "Mulai kunjungan",
        exact: true,
    });
    await expect(liveStart).toBeDisabled();
});
