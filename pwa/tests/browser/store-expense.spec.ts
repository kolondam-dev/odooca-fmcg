import { checkIn, expect, test } from "./session-fixture";
import { openActivity, saveVisitPhoto } from "./visit-helpers";

test("Biaya toko: komponen terisi menjadi pengajuan scope toko, Lainnya wajib keterangan", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await page
        .getByRole("button", { name: "Perbarui lokasi outlet", exact: true })
        .click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await page.getByRole("button", { name: /^Biaya toko/ }).click();
    const screen = page.getByRole("region", { name: "Biaya toko" });
    await expect(screen.getByText("Scope: toko")).toBeVisible();
    await screen.getByLabel("Parkir").fill("5000");
    await screen.getByLabel("Kuli bongkar").fill("40000");
    await screen.getByLabel("Lainnya", { exact: true }).fill("15000");
    await expect(
        screen.getByRole("button", { name: "Simpan biaya · Rp 60.000" }),
    ).toBeVisible();
    await screen.getByRole("button", { name: /^Simpan biaya/ }).click();
    await expect(screen.getByRole("alert")).toContainText(
        "Keterangan lainnya wajib",
    );
    await screen
        .getByLabel(/^Keterangan lainnya/)
        .fill("Uang kebersihan pasar");
    await screen.getByRole("button", { name: /^Simpan biaya/ }).click();
    await expect(screen).toHaveCount(0);
    await page
        .getByRole("button", { name: "Kembali", exact: true })
        .first()
        .click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await openActivity(page);
    await expect(page.getByText(/Biaya toko • .* • Rp\s5\.000/)).toBeVisible();
    await expect(page.getByText(/Biaya toko • .* • Rp\s40\.000/)).toBeVisible();
    await expect(page.getByText(/Biaya toko • .* • Rp\s15\.000/)).toBeVisible();
});
