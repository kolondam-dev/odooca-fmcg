import { checkIn, expect, test, type Page } from "./session-fixture";
import { saveVisitPhoto } from "./visit-helpers";

const PELANGI = { latitude: 1.456, longitude: 124.84 };
const SINAR_PAGI = { latitude: 1.465, longitude: 124.833 };

async function startVisit(
    page: Page,
    context: import("@playwright/test").BrowserContext,
    outlet: RegExp,
    at: { latitude: number; longitude: number },
) {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({ ...at, accuracy: 3 });
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: outlet }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
}

test("kartu Tagihan: piutang, faktur terbuka, dan wajib ditagih hari ini (jatuh tempo < 7 hari)", async ({
    page,
    context,
}) => {
    await startVisit(page, context, /Minimarket Pelangi/, PELANGI);
    const card = page
        .locator(".ui-card")
        .filter({ has: page.getByRole("heading", { name: "Tagihan" }) });
    await expect(card).toContainText("Wajib ditagih hari ini");
    await expect(card).toContainText(/1\.750\.000/); // piutang berjalan
    await expect(card).toContainText(/1\.550\.000\s*·\s*3 faktur/); // wajib ditagih
    const list = card.getByRole("list", { name: "Faktur terbuka" });
    await expect(list.getByRole("listitem")).toHaveCount(4);
    await expect(list).toContainText("Terlambat 34 hari");
    await expect(list).toContainText("Jatuh tempo 5 hari lagi");
    await expect(list).toContainText("Jatuh tempo 20 hari lagi");
    await expect(card).toContainText(
        "Pencatatan penagihan di aplikasi belum aktif",
    );
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
});

test("kartu Tagihan: outlet tanpa piutang tampil Tidak ada tagihan", async ({
    page,
    context,
}) => {
    await startVisit(page, context, /Toko Sinar Pagi/, SINAR_PAGI);
    const card = page
        .locator(".ui-card")
        .filter({ has: page.getByRole("heading", { name: "Tagihan" }) });
    await expect(card).toContainText("Tidak ada tagihan");
    await expect(card).toContainText("Tidak ada faktur terbuka");
    await expect(
        card.getByRole("list", { name: "Faktur terbuka" }),
    ).toHaveCount(0);
});
