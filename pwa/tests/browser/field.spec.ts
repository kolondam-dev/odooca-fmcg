import { expect, test } from "@playwright/test";
test("home is usable on phone/tablet with no overflow and local assets", async ({
    page,
}) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("./");
    await expect(
        page.getByRole("heading", { name: /Selamat bekerja/ }),
    ).toBeVisible();
    await expect(
        page.getByText("SIMULASI • Data fiktif, belum terhubung Odoo"),
    ).toBeVisible();
    await expect(
        page.getByRole("navigation", { name: "Navigasi utama" }),
    ).toBeVisible();
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
    await page.evaluate(() => document.fonts.ready);
    expect(errors).toEqual([]);
    expect(
        await page
            .locator(".icon")
            .first()
            .evaluate((el) => el.getBoundingClientRect().width),
    ).toBeLessThanOrEqual(32);
    await page.screenshot({
        path: `test-results/home-${test.info().project.name}.png`,
        fullPage: true,
    });
});
test("stacked roles and persona switch never show another persona queue", async ({
    page,
}) => {
    await page.goto("./");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByLabel("Persona demo").selectOption("delivery");
    await expect(page.getByRole("heading", { name: /Novry/ })).toBeVisible();
    await expect(
        page
            .getByRole("navigation")
            .getByRole("button", { name: "Sales", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page.getByLabel("Persona demo").selectOption("canvass");
    await expect(
        page
            .getByRole("navigation")
            .getByRole("button", { name: "Sales", exact: true }),
    ).toBeVisible();
    await expect(
        page
            .getByRole("navigation")
            .getByRole("button", { name: "Delivery", exact: true }),
    ).toBeVisible();
});
test("offline order survives reload, syncs on reconnect, stays separate across accounts", async ({
    page,
    context,
}) => {
    await page.goto("./");
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await page.getByLabel("Kuantitas Biskuit Kelapa 300 g").fill("2");
    await page.getByRole("button", { name: "Kembali", exact: true }).click();
    await page.reload();
    await page
        .getByRole("button", { name: "Buat order", exact: false })
        .click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await expect(page.getByLabel("Kuantitas Biskuit Kelapa 300 g")).toHaveValue(
        "2",
    );
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await page.getByRole("button", { name: "Simpan ke antrean demo" }).click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText("Menunggu koneksi", { exact: true }),
    ).toBeVisible();
    await page.reload();
    await expect(
        page.getByRole("heading", { name: /Selamat bekerja/ }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText("Menunggu koneksi", { exact: true }),
    ).toBeVisible();
    await context.setOffline(false);
    await expect(
        page.getByText("Diterima simulator", { exact: true }),
    ).toBeVisible({ timeout: 20000 });
    await page.getByLabel("Persona demo").selectOption("delivery");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText("Belum ada aktivitas. Mulai dari order atau pengajuan."),
    ).toBeVisible();
    await page.getByLabel("Persona demo").selectOption("sales");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(page.locator(".activity")).toHaveCount(1);
});
test("expense request is an approval request, not disbursement", async ({
    page,
}) => {
    await page.goto("./");
    await page
        .getByRole("button", { name: "Uang lapangan", exact: false })
        .click();
    await page
        .getByRole("combobox", { name: "Kategori", exact: true })
        .selectOption("fuel_emergency");
    await expect(
        page.getByText(
            "BBM insidentil: Supervisor + Branch Manager, berapa pun nominalnya.",
        ),
    ).toBeVisible();
    await page.getByLabel("Tanggal perjalanan").fill("2026-10-28");
    await page.getByLabel("Nominal pengajuan (Rp)").fill("100000");
    await page.getByLabel("KM / odometer awal").fill("15000");
    await page
        .getByLabel("Tujuan / alasan")
        .fill("Permohonan demo perjalanan luar kota");
    await page.getByRole("button", { name: "Simpan ke antrean demo" }).click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page
            .locator(".activity")
            .getByText("Menunggu approval", { exact: true }),
    ).toBeVisible();
});
test("missing evidence is not accepted as attendance", async ({
    page,
    context,
}) => {
    await context.clearPermissions();
    await page.goto("./");
    await page.getByRole("button", { name: "Absensi", exact: false }).click();
    await page.getByRole("button", { name: "Periksa kesiapan bukti" }).click();
    await expect(page.getByRole("alert")).toContainText(
        "Simpan foto dan lokasi dahulu.",
    );
});
test("live build is fail-closed with no simulation selector or data", async ({
    page,
}) => {
    await page.goto("http://127.0.0.1:4174/field/");
    await expect(
        page.getByText("Integrasi layanan perusahaan belum diaktifkan."),
    ).toBeVisible();
    await expect(page.getByLabel("Persona demo")).toHaveCount(0);
    await expect(page.getByText("Toko Sinar Pagi")).toHaveCount(0);
});
