import { expect, test } from "./session-fixture";
import { ensureDaily, switchPersona } from "./delivery-helpers";

test("Beranda Sales: outlet berikutnya, jarak, Navigasi ke outlet dan Mulai kunjungan", async ({
    page,
}) => {
    await page.goto("./");
    await ensureDaily(page);
    await expect(page.getByText(/Outlet berikutnya · 1 dari/)).toBeVisible();
    const nav = page.getByRole("link", {
        name: "Navigasi ke outlet",
        exact: true,
    });
    await expect(nav).toHaveAttribute(
        "href",
        /google\.com\/maps\/dir.*destination=/,
    );
    await expect(nav).toHaveAttribute("target", "_blank");
    await expect(nav).toHaveAttribute("rel", /noopener/);
    await expect(
        page.getByRole("button", { name: /^Mulai kunjungan · / }),
    ).toBeVisible();
    await expect(page.getByText("Lihat semua outlet")).toHaveCount(0);
    await expect(
        page.getByText("Order terkonfirmasi", { exact: true }),
    ).toBeVisible();
});

test("Beranda Delivery: statistik DO, Pengiriman berikutnya dan Mulai pengiriman", async ({
    page,
}) => {
    await page.goto("./");
    await ensureDaily(page);
    await switchPersona(page, "delivery");
    await ensureDaily(page);
    await expect(page.getByText("DO hari ini", { exact: true })).toBeVisible();
    await expect(page.getByText("Toko", { exact: true })).toBeVisible();
    await expect(page.getByText("Selesai", { exact: true })).toBeVisible();
    await expect(page.getByText("Pengiriman berikutnya")).toBeVisible();
    await expect(
        page.getByRole("link", { name: "Navigasi", exact: true }),
    ).toHaveAttribute("href", /destination=/);
    await page
        .getByRole("button", { name: "Mulai pengiriman", exact: true })
        .click();
    await expect(
        page.getByRole("heading", { name: "Delivery order hari ini" }),
    ).toBeVisible();
});

test("Beranda Canvasser: dua kartu Berikutnya, DO selesai x/y dan dua tombol aksi", async ({
    page,
}) => {
    await page.goto("./");
    await ensureDaily(page);
    await switchPersona(page, "canvass");
    await ensureDaily(page);
    await expect(page.getByText("Berikutnya", { exact: true })).toBeVisible();
    await expect(page.getByText("Kunjungan Sales")).toBeVisible();
    await expect(page.getByText(/^Pengiriman DEMO-DO-/)).toBeVisible();
    await expect(page.getByText("Belum mulai", { exact: true })).toBeVisible();
    await expect(page.getByText("DO selesai", { exact: true })).toBeVisible();
    await expect(page.getByText(/^0\/\d+$/).first()).toBeVisible();
    await expect(
        page.getByRole("button", { name: "Mulai kunjungan", exact: true }),
    ).toBeVisible();
    await page
        .getByRole("button", { name: "Mulai kirim", exact: true })
        .click();
    await expect(
        page.getByRole("heading", { name: "Delivery order hari ini" }),
    ).toBeVisible();
});

test("Tab bawah mengikuti peran: Sales, Delivery dan Canvasser sesuai DS", async ({
    page,
}) => {
    const tabs = async () =>
        page
            .getByRole("navigation", { name: "Navigasi utama" })
            .getByRole("button")
            .allInnerTexts();
    await page.goto("./");
    await ensureDaily(page);
    expect(await tabs()).toEqual(["Beranda", "Sales", "HRIS", "Lainnya"]);
    await switchPersona(page, "delivery");
    expect(await tabs()).toEqual(["Beranda", "Delivery", "HRIS", "Lainnya"]);
    await switchPersona(page, "canvass");
    expect(await tabs()).toEqual([
        "Beranda",
        "Sales",
        "Delivery",
        "HRIS",
        "Lainnya",
    ]);
});
