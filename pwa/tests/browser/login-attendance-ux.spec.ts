import { test, expect, checkIn } from "./session-fixture";

test("login stands alone, rejects wrong credentials and never exposes mock personas", async ({
    page,
}) => {
    await page.route("**/api/v1/me/bootstrap", (route) =>
        route.fulfill({ status: 401, json: { error: "not_authenticated" } }),
    );
    await page.route("**/web/login**", (route) =>
        route.fulfill({
            contentType: "text/html",
            body: '<form class="oe_login_form"><input name="csrf_token" value="csrf-test"><input name="password"></form>',
        }),
    );
    await page.goto("./");
    await expect(
        page.getByRole("heading", { name: "Masuk", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".topbar, .bottom-nav")).toHaveCount(0);
    await expect(
        page.getByText(/Hubungi admin atau line manager/),
    ).toBeVisible();
    await page.getByLabel("Nama pengguna").fill("wrong");
    await page
        .getByLabel("Kata sandi", { exact: true })
        .fill("invalid-password");
    await page.getByRole("button", { name: "Masuk", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(
        "Periksa nama pengguna",
    );
    await expect(page.getByLabel("Kata sandi", { exact: true })).toHaveValue(
        "",
    );
    await expect(page.getByLabel("Peran", { exact: true })).toHaveCount(0);
    await expect(page.locator(".greeting")).toHaveCount(0);
    await expect(
        page.getByRole("link", {
            name: "Ganti akun / keluar dari sesi sebelumnya",
        }),
    ).toHaveAttribute("href", "/web/session/logout?redirect=%2Ffield%2F");
    await page.screenshot({
        path: `test-results/login-${test.info().project.name}.png`,
        fullPage: true,
    });
});

test("native CSRF login opens real scoped workspace and full-width equal navigation", async ({
    page,
}) => {
    let authenticated = false,
        posted = false;
    await page.route("**/api/v1/me/bootstrap", (route) =>
        authenticated
            ? route.fallback()
            : route.fulfill({
                  status: 401,
                  json: { error: "not_authenticated" },
              }),
    );
    await page.route("**/web/login**", async (route) => {
        if (route.request().method() === "POST") {
            const body = new URLSearchParams(route.request().postData()!);
            expect(body.get("csrf_token")).toBe("csrf-login");
            expect(body.get("login")).toBe("employee");
            expect(body.get("password")).toBe("password-test-only");
            authenticated = true;
            posted = true;
            return route.fulfill({
                contentType: "text/html",
                body: "<main>Authenticated</main>",
            });
        }
        return route.fulfill({
            contentType: "text/html",
            body: '<form class="oe_login_form"><input name="csrf_token" value="csrf-login"><input name="db" value="test-db"></form>',
        });
    });
    await page.route("**/web/session/get_session_info", (route) =>
        route.fulfill({ json: { result: { uid: 12 } } }),
    );
    await page.goto("./");
    await page.getByLabel("Nama pengguna").fill("employee");
    await page
        .getByLabel("Kata sandi", { exact: true })
        .fill("password-test-only");
    await page.getByRole("button", { name: "Masuk", exact: true }).click();
    await expect(
        page.getByRole("heading", { name: /Selamat bekerja/ }),
    ).toBeVisible();
    expect(posted).toBe(true);
    await expect(page.locator(".topbar")).toContainText("Online");
    await expect(page.locator(".greeting .eyebrow")).toHaveText(
        /\d{2}[.:]\d{2}[.:]\d{2}.*WITA/,
    );
    const geometry = await page.evaluate(() => {
        const rect = (selector: string) =>
            document.querySelector(selector)!.getBoundingClientRect().toJSON();
        return {
            nav: rect(".bottom-nav"),
            columns: [...document.querySelectorAll(".bottom-nav button")].map(
                (el) => el.getBoundingClientRect().toJSON(),
            ),
            header: rect(".topbar"),
            logo: rect(".topbar .app-brand"),
            greeting: rect(".greeting"),
            morning: rect(".morning-card"),
            quick: rect(".quick-grid"),
            width: innerWidth,
        };
    });
    expect(geometry.columns).toHaveLength(4);
    expect(Math.abs(geometry.nav.width - geometry.width)).toBeLessThan(2);
    for (const col of geometry.columns)
        expect(Math.abs(col.width - geometry.nav.width / 4)).toBeLessThan(1);
    expect(geometry.logo.height).toBe(geometry.header.height);
    expect(geometry.morning.top).toBeGreaterThanOrEqual(
        geometry.greeting.bottom,
    );
    expect(geometry.quick.top).toBeGreaterThanOrEqual(geometry.morning.bottom);
    await expect(
        page.getByRole("button", { name: /Buat order/ }),
    ).toBeDisabled();
    await expect(
        page.getByRole("button", { name: /Uang lapangan/ }),
    ).toBeDisabled();
    await expect(
        page.getByRole("button", { name: "Buka sesi kerja", exact: true }),
    ).toBeDisabled();
    expect(
        await page.evaluate(() =>
            JSON.stringify({ ...localStorage, ...sessionStorage }),
        ),
    ).not.toContain("password-test-only");
    await page.screenshot({
        path: `test-results/home-new-${test.info().project.name}.png`,
        fullPage: true,
    });
});

test("check-in is a full page with map, bound watermark photo and clock-out", async ({
    page,
}) => {
    await page.goto("./");
    await checkIn(page);
    await expect(
        page.getByRole("button", { name: /Buat order/ }),
    ).toBeEnabled();
    await expect(page.locator(".quick-attendance-record")).toContainText(
        "Clock in",
    );
    await page.getByRole("button", { name: "Clock out", exact: true }).click();
    const form = page.getByRole("dialog");
    await expect(form.getByLabel("Aktivitas")).toHaveValue("check_out");
    const bounds = await form.boundingBox();
    expect(bounds!.y).toBe(0);
    expect(bounds!.height).toBe(await page.evaluate(() => innerHeight));
    await page
        .getByRole("button", { name: "Ambil Lokasi Presisi", exact: true })
        .click();
    await expect(
        page.getByRole("region", { name: "Lokasi dan foto absensi" }),
    ).toHaveAttribute("aria-busy", "false");
    await page
        .getByLabel("Alamat / nama lokasi")
        .fill("Jl. Sam Ratulangi, Sario, Manado, Sulawesi Utara");
    await page
        .getByRole("button", { name: "Buka Kamera", exact: true })
        .click();
    await page
        .getByLabel("Buka Kamera Perangkat")
        .setInputFiles("public/icon-192.png");
    await expect(
        page.getByAltText("Foto absensi dengan watermark"),
    ).toBeVisible();
    await expect(page.locator(".attendance-result")).toContainText(
        "PT. Demo FMCG · Andre",
    );
    await expect(
        page.getByAltText("Foto absensi dengan watermark"),
    ).toBeInViewport();
    await expect(page.locator(".attendance-result")).toContainText("Manado");
    await page.screenshot({
        path: `test-results/attendance-${test.info().project.name}.png`,
        fullPage: true,
    });
    await page.getByRole("button", { name: "Check out", exact: true }).click();
    await expect(form).toHaveCount(0);
    await expect(
        page.getByRole("button", { name: /Buat order/ }),
    ).toBeDisabled();
    await page.reload();
    await expect(page.locator(".quick-attendance-record")).toContainText(
        "Clock out",
    );
});

test("denied GPS keeps check-in disabled and returning restores focus", async ({
    page,
    context,
}) => {
    await context.clearPermissions();
    await page.addInitScript(() => {
        navigator.geolocation.getCurrentPosition = (_ok, fail) =>
            fail?.({
                code: 1,
                message: "denied",
                PERMISSION_DENIED: 1,
                POSITION_UNAVAILABLE: 2,
                TIMEOUT: 3,
            });
    });
    await page.goto("./");
    const attendance = page.getByRole("button", { name: /^Absensi/ }).first();
    await attendance.click();
    await expect(page.getByRole("alert")).toContainText("Izin lokasi ditolak");
    await expect(
        page.getByRole("button", { name: "Check in", exact: true }),
    ).toBeDisabled();
    await expect(
        page.getByRole("button", { name: "Buka Kamera", exact: true }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "Kembali", exact: true }).click();
    await expect(attendance).toBeFocused();
});

test("expired session clears the workspace before another account can enter", async ({
    page,
}) => {
    await page.goto("./");
    await expect(page.locator(".greeting")).toBeVisible();
    await page.route("**/api/v1/me/bootstrap", (route) =>
        route.fulfill({ status: 401, json: { error: "not_authenticated" } }),
    );
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(
        page.getByRole("heading", { name: "Masuk", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".topbar, .bottom-nav, .greeting")).toHaveCount(
        0,
    );
    await expect(page.getByRole("alert")).toContainText("Sesi berakhir");
});

for (const retake of [false, true])
    test(`snapshot failure retry binds the displayed photo after reload; retake=${retake}`, async ({
        page,
        context,
    }) => {
        await context.grantPermissions(["geolocation"]);
        let failNextSnapshot = false;
        await page.route("**/api/v1/sync/snapshot", (route) => {
            if (!failNextSnapshot) return route.fallback();
            failNextSnapshot = false;
            return route.fulfill({
                status: 503,
                json: { error: "snapshot unavailable" },
            });
        });
        await page.goto("./");
        await page
            .getByRole("button", { name: /^Absensi/ })
            .first()
            .click();
        async function photo(address: string) {
            await page
                .getByRole("button", {
                    name: "Ambil Lokasi Presisi",
                    exact: true,
                })
                .click();
            await expect(
                page.getByRole("region", { name: "Lokasi dan foto absensi" }),
            ).toHaveAttribute("aria-busy", "false");
            await page.getByLabel("Alamat / nama lokasi").fill(address);
            await page
                .getByRole("button", {
                    name: /^(Buka Kamera|Foto ulang)$/,
                    exact: true,
                })
                .click();
            await page
                .getByLabel("Buka Kamera Perangkat")
                .setInputFiles("public/icon-192.png");
            await expect(
                page.getByAltText("Foto absensi dengan watermark"),
            ).toBeInViewport();
            await expect(
                page.getByRole("button", { name: "Check in", exact: true }),
            ).toBeEnabled();
        }
        const pending = () =>
            page.evaluate(async () => {
                const db = await new Promise<IDBDatabase>((resolve) => {
                    const request = indexedDB.open("fmcg-field-demo-v1");
                    request.onsuccess = () => resolve(request.result);
                });
                const result = await new Promise<any>((resolve) => {
                    const request = db
                        .transaction("drafts")
                        .objectStore("drafts")
                        .get("demo-mdu:DEMO-ANDRE:morning-session-v1");
                    request.onsuccess = () => resolve(request.result?.value);
                });
                db.close();
                return result;
            });
        await photo("Alamat foto A, Manado");
        failNextSnapshot = true;
        await page
            .getByRole("button", { name: "Check in", exact: true })
            .click();
        await expect(page.getByRole("alert")).toContainText("503");
        const a = await pending();
        expect(a.sessionId).toBeNull();
        expect(a.attendanceEvidence.packageHash).toMatch(/^[a-f0-9]{64}$/);
        if (retake) await photo("Alamat foto B, lokasi pengganti, Manado");
        const selected = await page
            .getByAltText("Foto absensi dengan watermark")
            .evaluate(async (image: HTMLImageElement) => {
                const blob = await (await fetch(image.src)).blob();
                const hash = [
                    ...new Uint8Array(
                        await crypto.subtle.digest(
                            "SHA-256",
                            await blob.arrayBuffer(),
                        ),
                    ),
                ]
                    .map((n) => n.toString(16).padStart(2, "0"))
                    .join("");
                const db = await new Promise<IDBDatabase>((resolve) => {
                    const request = indexedDB.open("fmcg-field-demo-v1");
                    request.onsuccess = () => resolve(request.result);
                });
                const rows = await new Promise<any[]>((resolve) => {
                    const request = db
                        .transaction("evidence")
                        .objectStore("evidence")
                        .getAll();
                    request.onsuccess = () => resolve(request.result);
                });
                db.close();
                const row = rows.find(
                    (row) => row.visual?.photoSha256 === hash,
                );
                if (!row)
                    throw new Error(
                        "Displayed photo has no matching stored package",
                    );
                return {
                    id: row.key.slice(row.owner.length + 1),
                    packageHash: row.visual.bindingSha256,
                };
            });
        if (retake) expect(selected.id).not.toBe(a.attendanceEvidence.id);
        else expect(selected.id).toBe(a.attendanceEvidence.id);
        await page
            .getByRole("button", { name: "Check in", exact: true })
            .click();
        await expect(page.locator(".quick-attendance-record")).toBeVisible();
        const opened = await pending();
        expect(opened.attendanceEvidence).toMatchObject(selected);
        expect(opened.sessionId).toBeTruthy();
        await page.reload();
        await expect(page.locator(".quick-attendance-record")).toBeVisible();
        expect(await pending()).toEqual(opened);
    });
