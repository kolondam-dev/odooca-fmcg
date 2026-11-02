import { test, expect, checkIn, changeTestAccount } from "./session-fixture";
import { saveVisitPhoto } from "./visit-helpers";

test("browser Back closes camera before form and returns through pages", async ({
    page,
}) => {
    await page.goto("./");
    await page.getByRole("button", { name: "HRIS", exact: true }).click();
    await page.getByRole("button", { name: /Pengajuan cuti/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.goBack();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page).toHaveURL(/#hris$/);
    await page.goBack();
    await expect(page).toHaveURL(/#home$/);
    await page.context().grantPermissions(["geolocation"]);
    await page.getByRole("button", { name: /^Absensi/ }).click();
    await page.getByLabel("Alamat / nama lokasi").fill("Kantor Manado");
    await page
        .getByRole("button", { name: "Buka Kamera", exact: true })
        .click();
    await expect(page.locator("[role=dialog][aria-modal=true]")).toHaveCount(1);
    const camera = page.locator(".camera-modal-backdrop");
    await expect(camera).toBeVisible();
    await camera.getByRole("button", { name: /Batal/ }).focus();
    await page.keyboard.press("Tab");
    expect(
        await camera.evaluate((el) => el.contains(document.activeElement)),
    ).toBe(true);
    await page.goBack();
    await expect(camera).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(1);
    await page.goBack();
    await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("shell keeps header and nav stable while HRIS and More scroll internally", async ({
    page,
}) => {
    await page.goto("./");
    const profile = (await page
        .getByRole("button", { name: "Profil dan Sesi Akun", exact: true })
        .boundingBox())!;
    expect(profile.width).toBeGreaterThanOrEqual(44);
    expect(profile.height).toBeGreaterThanOrEqual(44);
    const header = page.locator(".header-fixed"),
        nav = page.locator(".bottom-nav");
    for (const name of ["HRIS", "Lainnya"]) {
        await page.getByRole("button", { name, exact: true }).click();
        const before = {
            h: await header.boundingBox(),
            n: await nav.boundingBox(),
        };
        await page.locator("#main-content").evaluate((el) => {
            el.scrollTop = el.scrollHeight;
        });
        expect((await header.boundingBox())!.y).toBe(before.h!.y);
        expect((await nav.boundingBox())!.y).toBe(before.n!.y);
        expect(await page.evaluate(() => scrollY)).toBe(0);
        expect(
            await page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
            ),
        ).toBe(true);
    }
});

test("search Back restores list and compact POS toolbar leaves product space on short screens", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByLabel("Cari outlet", { exact: true }).click();
    await page.getByRole("searchbox").fill("Sinar");
    await page.goBack();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByLabel("Cari outlet", { exact: true })).toHaveValue(
        "Sinar",
    );
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await page
        .getByRole("button", { name: "Open session", exact: true })
        .click();
    await page.setViewportSize({ width: 393, height: 430 });
    await page.locator(".sheet-body").evaluate((el) => {
        el.scrollTop = 600;
    });
    const tabs = (await page
        .getByRole("navigation", { name: "Tahap order" })
        .boundingBox())!;
    const toolbar = (await page.locator(".pos-toolbar").boundingBox())!;
    const body = (await page.locator(".sheet-body").boundingBox())!;
    expect(toolbar.y).toBeGreaterThanOrEqual(tabs.y + tabs.height - 1);
    expect(toolbar.height).toBeLessThan(115);
    expect(body.height - tabs.height - toolbar.height).toBeGreaterThan(70);
    const search = (await page
        .getByLabel("Cari produk", { exact: true })
        .boundingBox())!;
    const icon = (await page.locator(".product-search svg").boundingBox())!;
    expect(
        Math.abs(search.y + search.height / 2 - icon.y - icon.height / 2),
    ).toBeLessThan(3);
});

test("expense references are contextual and dates have Indonesian selected value", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await page
        .getByRole("button", { name: /Uang lapangan/ })
        .first()
        .click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByLabel("Referensi trip / perjalanan")).toHaveValue(
        "TRIP-01",
    );
    await expect(
        dialog.getByLabel("Referensi DO (untuk biaya per pengiriman)"),
    ).toHaveCount(0);
    await dialog.getByLabel("Lingkup biaya").selectOption("delivery");
    await expect(
        dialog.getByLabel("Referensi DO (untuk biaya per pengiriman)"),
    ).toHaveCount(1);
    await dialog.getByLabel("Tanggal perjalanan").fill("2026-11-01");
    await expect(
        dialog.getByText("1 November 2026", { exact: true }),
    ).toBeVisible();
    await dialog.getByLabel("Lingkup biaya").selectOption("trip");
    await expect(
        dialog.getByLabel("Referensi DO (untuk biaya per pengiriman)"),
    ).toHaveCount(0);
});

test("map zoom and consent survive a new GPS fix, touch affects only the map", async ({
    page,
}, info) => {
    await page.context().grantPermissions(["geolocation"]);
    await page.route("https://tile.openstreetmap.org/**", (route) =>
        route.fulfill({
            path: "public/icon-192.png",
            contentType: "image/png",
        }),
    );
    await page.goto("./");
    await page.getByRole("button", { name: /^Absensi/ }).click();
    const region = page.getByRole("region", {
        name: "Preview peta Kantor Pusat",
        exact: true,
    });
    await region
        .getByRole("button", { name: "Muat peta jalan", exact: true })
        .click();
    const map = region.locator(".interactive-map");
    await expect(map).toHaveAttribute("data-zoom", /\d+/);
    const initialZoom = Number(await map.getAttribute("data-zoom"));
    const zoomOutBtn = region.getByRole("button", {
        name: "Perkecil peta",
        exact: true,
    });
    await zoomOutBtn.scrollIntoViewIfNeeded();
    await zoomOutBtn.click();
    await expect
        .poll(async () => Number(await map.getAttribute("data-zoom")), {
            timeout: 10000,
        })
        .toBeLessThan(initialZoom);
    const zoom = await map.getAttribute("data-zoom");
    await page.context().setGeolocation({
        latitude: 1.46502,
        longitude: 124.83302,
        accuracy: 2,
    });
    await page
        .getByRole("button", { name: "Ambil Lokasi Presisi", exact: true })
        .click();
    await expect(region).toContainText("1.465020");
    await expect(map).toHaveAttribute("data-zoom", zoom!);
    await expect(
        region.getByRole("button", { name: "Tutup peta jalan", exact: true }),
    ).toBeVisible();
    if (info.project.name === "phone") {
        await map.scrollIntoViewIfNeeded();
        const box = (await map.boundingBox())!;
        const cdp = await page.context().newCDPSession(page);
        const x = box.x + box.width / 2,
            y = box.y + box.height / 2;
        const scale = await page.evaluate(() => visualViewport!.scale);
        const points = (offset: number) => [
            { x: x - offset, y, id: 1 },
            { x: x + offset, y, id: 2 },
        ];
        await cdp.send("Input.dispatchTouchEvent", {
            type: "touchStart",
            touchPoints: points(30),
        });
        for (const offset of [40, 50, 65, 80])
            await cdp.send("Input.dispatchTouchEvent", {
                type: "touchMove",
                touchPoints: points(offset),
            });
        await cdp.send("Input.dispatchTouchEvent", {
            type: "touchEnd",
            touchPoints: [],
        });
        await expect(map).not.toHaveAttribute("data-zoom", zoom!);
        expect(await page.evaluate(() => visualViewport!.scale)).toBe(scale);
        await cdp.detach();
    }
});

test("500 SKU catalog renders bounded rows and preserves selected off-screen quantities", async ({
    page,
}) => {
    const { MockProvider } = await import("../../src/data/mock");
    const snapshot = await new MockProvider("sales", true).snapshot();
    snapshot.products = Array.from({ length: 500 }, (_, i) => ({
        ...snapshot.products[0],
        id: `sku-${i}`,
        sku_code: `SKU-${i}`,
        name: `Produk ${i}`,
    }));
    await page.route("**/api/v1/sync/snapshot", (route) =>
        route.fulfill({
            json: {
                ...snapshot,
                office: {
                    id: "1",
                    name: "Kantor Pusat",
                    latitude: 1.465,
                    longitude: 124.833,
                    radius: 15,
                    coordinate_status: "test",
                },
            },
        }),
    );
    await page.goto("./");
    await checkIn(page);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    await saveVisitPhoto(page, "check-in");
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await page
        .getByRole("button", { name: "Open session", exact: true })
        .click();
    await expect(page.locator(".product-card")).toHaveCount(60);
    await page.getByLabel("Cari produk", { exact: true }).fill("SKU-499");
    await expect(page.locator(".product-card")).toHaveCount(1);
    await page.getByLabel("Kuantitas Produk 499", { exact: true }).fill("2");
    await page.getByLabel("Cari produk", { exact: true }).fill("");
    await expect(page.locator(".product-card")).toHaveCount(60);
    await page.getByLabel("Cari produk", { exact: true }).fill("SKU-499");
    await expect(
        page.getByLabel("Kuantitas Produk 499", { exact: true }),
    ).toHaveValue("2");
});

test("camera evidence saves one bound package automatically without a second location/save step", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    const feedback = (await page.locator(".toast").boundingBox())!;
    const main = (await page.locator("#main-content").boundingBox())!;
    expect(feedback.y + feedback.height).toBeLessThanOrEqual(main.y + 1);
    await page.getByRole("button", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: /Toko Sinar Pagi/ }).click();
    const group = page.getByRole("group", {
        name: "Foto check-in kunjungan",
        exact: true,
    });
    await group
        .getByRole("button", { name: "Buka Kamera Bukti", exact: true })
        .click();
    await page
        .getByLabel("Buka Kamera Perangkat")
        .setInputFiles("public/icon-192.png");
    await expect(
        group.getByText("Paket foto tersimpan untuk check-in outlet ini.", {
            exact: true,
        }),
    ).toBeVisible();
    await expect(
        group.getByRole("button", {
            name: "Ambil lokasi sekarang",
            exact: true,
        }),
    ).toHaveCount(0);
    await expect(
        group.getByRole("button", { name: "Simpan bukti lokal", exact: true }),
    ).toHaveCount(0);
    const binding = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const drafts = await new Promise<any[]>((resolve) => {
            const r = db.transaction("drafts").objectStore("drafts").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        db.close();
        return drafts.find(
            (row) => row.key.includes("visit-photo-v1:") && row.value?.ref,
        )?.value?.ref?.packageHash;
    });
    expect(binding).toMatch(/^[a-f0-9]{64}$/);
    await page
        .getByRole("button", { name: "Mulai kunjungan", exact: true })
        .click();
    await expect(
        page.getByText("Kunjungan lokal aktif", { exact: true }),
    ).toBeVisible();
});

test("account handover with nested camera restores body scroll and clears both dialogs", async ({
    page,
}) => {
    await page.context().grantPermissions(["geolocation"]);
    await page.goto("./");
    const overflow = await page.evaluate(() => document.body.style.overflow);
    await page.getByRole("button", { name: /^Absensi/ }).click();
    await page.getByLabel("Alamat / nama lokasi").fill("Kantor Manado");
    await page
        .getByRole("button", { name: "Buka Kamera", exact: true })
        .click();
    await expect(page.locator(".camera-modal-backdrop")).toBeVisible();
    await changeTestAccount(page, "delivery");
    await expect(
        page.getByRole("button", { name: "Profil dan Sesi Akun", exact: true }),
    ).toHaveText("N");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect
        .poll(() => page.evaluate(() => document.body.style.overflow))
        .toBe(overflow);
    await page.goBack();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: "Profil dan Sesi Akun", exact: true }),
    ).toHaveText("N");
});
