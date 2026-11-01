import { expect, test } from "./session-fixture";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
test.use({
    baseURL: "http://127.0.0.1:4175/field/",
    geolocation: { latitude: 1.465, longitude: 124.833, accuracy: 1 },
    permissions: ["geolocation"],
});
for (const denied of [false, true])
    test(`official capture multipart and private derivative, session denied=${denied}`, async ({
        page,
    }) => {
        await page.clock.install({ time: new Date("2026-10-29T01:00:00Z") });
        const photo = readFileSync("public/icon-192.png"),
            hash = createHash("sha256").update(photo).digest("hex");
        let posts = 0;
        await page.route("**/api/**", async (route) => {
            const path = new URL(route.request().url()).pathname;
            if (path.endsWith("/bootstrap"))
                return route.fulfill({
                    contentType: "application/json",
                    body: JSON.stringify({
                        id: "41",
                        companyId: "7",
                        name: "Capture User",
                        title: "",
                        roles: ["sales"],
                        capabilities: ["evidence.capture"],
                        csrfToken: "fixture-csrf",
                        businessDate: "2026-10-29",
                    }),
                });
            if (path.endsWith("/snapshot"))
                return route.fulfill({
                    contentType: "application/json",
                    body: JSON.stringify({
                        catalog_version: 2,
                        scope: {
                            company_id: "7",
                            user_id: "41",
                            warehouse_id: "9",
                            business_date: "2026-10-29",
                        },
                        version: "fixture-v1",
                        updatedAt: "2026-10-29T01:00:00Z",
                        products: [],
                        deliveries: [],
                        outlets: [
                            {
                                id: "12",
                                name: "Outlet Capture",
                                address: "Jalan Uji",
                                channel: "GT",
                                time: "",
                                distance: "",
                                latitude: 1.465,
                                longitude: 124.833,
                                radius: 10,
                            },
                        ],
                    }),
                });
            if (path === "/api/v1/evidence") {
                posts++;
                expect(route.request().method()).toBe("POST");
                const data = route.request().postDataBuffer()!.toString();
                expect(data).toContain('name="csrf_token"');
                expect(data).toContain("fixture-csrf");
                const metadata = JSON.parse(
                    data.match(/name="metadata"\r\n\r\n([^\r]+)/)![1],
                );
                expect(metadata.latitude).toBe(1.465);
                expect(metadata).not.toHaveProperty("radius");
                if (denied)
                    return route.fulfill({
                        status: 403,
                        contentType: "application/json",
                        body: '{"error":"forbidden"}',
                    });
                return route.fulfill({
                    status: 201,
                    contentType: "application/json",
                    body: JSON.stringify({
                        ...metadata,
                        user_id: "41",
                        company_id: "7",
                        warehouse_id: "9",
                        assignment_id: "13",
                        received_at: "2026-10-29T01:00:01Z",
                        master_latitude: 1.465,
                        master_longitude: 124.833,
                        distance_m: 0,
                        radius_m: 10,
                        original_sha256: hash,
                        watermarked_sha256: hash,
                        binding_sha256: "a".repeat(64),
                        original_url: `/api/v1/evidence/${metadata.client_uuid}/original`,
                        watermarked_url: `/api/v1/evidence/${metadata.client_uuid}/watermarked`,
                    }),
                });
            }
            if (path.endsWith("/watermarked"))
                return route.fulfill({ contentType: "image/png", body: photo });
            return route.abort();
        });
        await page.goto("./");
        await page
            .getByRole("button", { name: "Daily sync", exact: true })
            .click();
        await expect(
            page.getByRole("heading", { name: "Bukti foto resmi · staging" }),
        ).toBeVisible();
        await page
            .getByLabel("Foto sumber JPEG/PNG")
            .setInputFiles("public/icon-192.png");
        await page
            .getByRole("button", { name: "Ambil GPS bukti", exact: true })
            .click();
        await page
            .getByRole("button", {
                name: "Unggah bukti ke server",
                exact: true,
            })
            .click();
        if (denied) {
            await expect(
                page
                    .getByRole("status")
                    .filter({ hasText: "Sesi/scope bukti berubah" }),
            ).toContainText("Sesi/scope bukti berubah");
            await expect(
                page.getByText("Capture User", { exact: true }),
            ).toHaveCount(0);
            await expect(
                page.getByRole("heading", {
                    name: "Bukti foto resmi · staging",
                }),
            ).toHaveCount(0);
        } else {
            await expect(
                page.getByText("Bukti tersimpan di server.", { exact: true }),
            ).toBeVisible();
            await expect(
                page.getByRole("img", { name: "Foto watermark dari server" }),
            ).toBeVisible();
            await expect(
                page.getByText("Diterima server:", { exact: false }),
            ).toBeVisible();
            await expect(
                page.getByRole("button", {
                    name: "Unggah bukti ke server",
                    exact: true,
                }),
            ).toBeDisabled();
        }
        expect(posts).toBe(1);
        expect(
            await page.evaluate(
                async () => (await indexedDB.databases()).length,
            ),
        ).toBe(0);
    });
