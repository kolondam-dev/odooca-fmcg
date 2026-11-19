import { test, expect, checkIn } from "./session-fixture";
import {
    activity,
    leaveVisit,
    openActivity,
    saveVisitPhoto,
} from "./visit-helpers";

test("Riwayat: waktu kejadian lengkap sampai detik (HH.mm.ss), bukan HH.mm saja", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await leaveVisit(page);
    await openActivity(page);
    const rows = activity(page);
    await expect(rows.first()).toBeVisible();
    const times = (await rows.allInnerTexts())
        .join("\n")
        .match(/\b\d{2}\.\d{2}(?:\.\d{2})?\b/g);
    expect(times?.length ?? 0).toBeGreaterThan(0);
    for (const t of times ?? []) expect(t).toMatch(/^\d{2}\.\d{2}\.\d{2}$/);
});
