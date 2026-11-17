import { expect, test } from "./session-fixture";
import { ensureDaily, switchPersona } from "./delivery-helpers";

const GOOGLE_MAPS = /google\.com\/maps\/dir.*destination=-?\d/;

test("Navigasi Sales: layar DS, jarak garis lurus, Google Maps dan Saya sudah tiba", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 5,
    });
    await page.goto("./");
    await ensureDaily(page);
    const start = page.getByRole("button", { name: /^Mulai kunjungan · / });
    const outletName = (await start.innerText()).replace(
        /^Mulai kunjungan · /,
        "",
    );
    await page
        .getByRole("button", { name: "Navigasi ke outlet", exact: true })
        .click();

    const screen = page.getByRole("region", { name: "Navigasi", exact: true });
    await expect(
        screen.getByRole("heading", { name: "Navigasi", level: 1 }),
    ).toBeVisible();
    await expect(screen.getByRole("img", { name: "Peta area" })).toBeVisible();
    await expect(
        screen.getByText("Skema garis lurus, bukan rute jalan"),
    ).toBeVisible();
    await expect(
        screen.getByRole("heading", { name: outletName, level: 2 }),
    ).toBeVisible();
    await expect(screen.getByText(/km \(garis lurus\)/)).toBeVisible();
    const maps = screen.getByRole("link", { name: "Buka di Google Maps" });
    await expect(maps).toHaveAttribute("href", GOOGLE_MAPS);
    await expect(maps).toHaveAttribute("target", "_blank");
    await expect(maps).toHaveAttribute("rel", /noopener/);

    await screen
        .getByRole("button", {
            name: "Saya sudah tiba · Check-in",
            exact: true,
        })
        .click();
    await expect(screen).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: /Mulai kunjungan/ }).first(),
    ).toBeVisible();
});

test("Navigasi: Kembali dan tombol Back browser menutup layar tanpa pindah halaman", async ({
    page,
}) => {
    await page.goto("./");
    await ensureDaily(page);
    const open = () =>
        page
            .getByRole("button", { name: "Navigasi ke outlet", exact: true })
            .click();
    const screen = page.getByRole("region", { name: "Navigasi", exact: true });

    await open();
    await expect(screen).toBeVisible();
    await screen.getByRole("button", { name: "Kembali" }).click();
    await expect(screen).toHaveCount(0);
    await expect(page.getByText(/Outlet berikutnya · 1 dari/)).toBeVisible();

    await open();
    await expect(screen).toBeVisible();
    await page.goBack();
    await expect(screen).toHaveCount(0);
    await expect(page.getByText(/Outlet berikutnya · 1 dari/)).toBeVisible();
});

test("Navigasi: URL tidak membawa koordinat dan lokasi ditolak di mode live tidak memalsukan jarak", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    // Mode live eksplisit: izin ditolak hanya jatuh ke simulasi di mode demo.
    await page.addInitScript(() =>
        localStorage.setItem("fmcg:running-mode", "live"),
    );
    await page.goto("./");
    await ensureDaily(page);
    await page.evaluate(() => {
        navigator.geolocation.getCurrentPosition = (_ok, fail) =>
            fail?.({
                code: 1,
                message: "denied",
            } as GeolocationPositionError);
    });
    await page
        .getByRole("button", { name: "Navigasi ke outlet", exact: true })
        .click();
    const screen = page.getByRole("region", { name: "Navigasi", exact: true });
    await expect(
        screen.getByText(/Lokasi perangkat belum tersedia/),
    ).toBeVisible();
    await expect(screen.getByText(/garis lurus\)/)).toHaveCount(0);
    await expect(screen.getByText(/posisi simulasi/)).toHaveCount(0);
    // Google Maps tetap bisa dibuka tanpa lokasi perangkat.
    await expect(
        screen.getByRole("link", { name: "Buka di Google Maps" }),
    ).toHaveAttribute("href", GOOGLE_MAPS);
    expect(page.url()).not.toMatch(/\d+\.\d{3,}/);
});

test("Navigasi Delivery: dari Beranda dan dari daftar toko, tiba membuka hub toko", async ({
    page,
    context,
}) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 5,
    });
    await page.goto("./");
    await ensureDaily(page);
    await switchPersona(page, "delivery");
    await ensureDaily(page);

    // Dari Beranda.
    await page.getByRole("button", { name: "Navigasi", exact: true }).click();
    const screen = page.getByRole("region", { name: "Navigasi", exact: true });
    await expect(screen).toBeVisible();
    await expect(
        screen.getByRole("link", { name: "Buka di Google Maps" }),
    ).toHaveAttribute("href", GOOGLE_MAPS);
    await screen
        .getByRole("button", {
            name: "Saya sudah tiba · Check-in",
            exact: true,
        })
        .click();
    await expect(screen).toHaveCount(0);
    await expect(
        page.getByRole("region", { name: /^Delivery DEMO-DO-/ }),
    ).toBeVisible();

    // Dari daftar toko di tab Delivery.
    await page
        .getByRole("region", { name: /^Delivery DEMO-DO-/ })
        .getByRole("button", { name: "Kembali" })
        .first()
        .click();
    const stores = page.getByRole("region", { name: /^Daftar toko / });
    if (!(await stores.isVisible()))
        await page
            .getByRole("button", { name: /^Buka TRIP/ })
            .first()
            .click();
    await stores
        .getByRole("button", { name: "Navigasi", exact: true })
        .first()
        .click();
    await expect(screen).toBeVisible();
    await screen.getByRole("button", { name: "Kembali" }).click();
    await expect(screen).toHaveCount(0);
    await expect(stores).toBeVisible();
});
