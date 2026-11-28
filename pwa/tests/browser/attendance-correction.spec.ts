import { expect, test } from "@playwright/test";

const csrfToken = "fixture-csrf";
const reference = "Karyawan Fixture · 2026-11-25 · 08:00–17:00 WITA";

test("approver sees the active tier and sends the decision for that tier", async ({
    page,
}) => {
    let approved = false;
    await page.route("**/api/v1/attendance/corrections", (route) =>
        route.fulfill({
            json: {
                csrfToken,
                items: [
                    {
                        id: 42,
                        reference,
                        reason: "Lupa absen pulang",
                        state: approved ? "approved" : "pending",
                        tier: 3,
                        canDecide: !approved,
                        mine: false,
                        steps: [
                            {
                                name: "Owner",
                                state: approved ? "approved" : "pending",
                                actor: approved ? "Owner Fixture" : "",
                                notes: "",
                            },
                        ],
                    },
                ],
            },
        }),
    );
    await page.route(
        "**/api/v1/attendance/corrections/decision",
        async (route) => {
            const fields = new URLSearchParams(
                route.request().postData() ?? "",
            );
            expect(Object.fromEntries(fields)).toEqual({
                approval_id: "42",
                tier: "3",
                decision: "approve",
                notes: "Sudah diperiksa",
                csrf_token: csrfToken,
            });
            approved = true;
            await route.fulfill({ json: {} });
        },
    );
    await page.goto("/field/?attendance-approval");
    const card = page.getByRole("article").filter({ hasText: reference });
    await expect(card.getByRole("button", { name: "Setujui" })).toBeVisible();
    await card.getByLabel("Catatan").fill("Sudah diperiksa");
    await card.getByRole("button", { name: "Setujui" }).click();
    await expect(card.getByText(/Owner Fixture/)).toBeVisible();
    await expect(card.getByRole("button", { name: "Setujui" })).toHaveCount(0);
});

test("ambiguous submit keeps the same correction key on retry", async ({
    page,
}) => {
    const keys: string[] = [];
    await page.route("**/api/v1/attendance/corrections", async (route) => {
        if (route.request().method() === "GET") {
            await route.fulfill({ json: { items: [], csrfToken } });
            return;
        }
        const fields = new URLSearchParams(route.request().postData() ?? "");
        keys.push(fields.get("client_key") ?? "");
        if (keys.length === 1) {
            await route.abort("failed");
            return;
        }
        await route.fulfill({ json: {} });
    });
    await page.goto("/field/?attendance-approval");
    await page.getByLabel("Tanggal", { exact: true }).fill("2026-11-25");
    await page.getByLabel("Masuk", { exact: true }).fill("08:00");
    await page.getByLabel("Pulang", { exact: true }).fill("17:00");
    await page.getByLabel("Alasan", { exact: true }).fill("Lupa absen pulang");
    const submit = page.getByRole("button", { name: "Kirim pengajuan" });
    await submit.click();
    await expect.poll(() => keys.length).toBe(1);
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect.poll(() => keys.length).toBe(2);
    expect(keys[0]).toMatch(/^[a-f0-9-]{36}$/);
    expect(keys[1]).toBe(keys[0]);
});
