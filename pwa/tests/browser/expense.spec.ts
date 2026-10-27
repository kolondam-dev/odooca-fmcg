import { expect, test, type Page, type BrowserContext } from "@playwright/test";
async function requestAdvance(page: Page, category = "meal") {
    await page.clock.install({ time: new Date("2026-10-27T00:00:00Z") });
    await page.goto("./");
    await page
        .getByRole("button", { name: "Uang lapangan", exact: false })
        .click();
    await page.getByLabel("Kategori", { exact: true }).selectOption(category);
    await page.getByLabel("Referensi trip / perjalanan").fill("TRIP-DEMO-01");
    await page.getByLabel("Tanggal perjalanan").fill("2026-10-28");
    await page.getByLabel("Nominal pengajuan (Rp)").fill("200000");
    if (category.startsWith("fuel"))
        await page.getByLabel("KM / odometer awal").fill("1000");
    await page
        .getByLabel("Tujuan / alasan")
        .fill("Uang lapangan simulasi luar kota");
    await page.getByRole("button", { name: "Simpan ke antrean demo" }).click();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page
            .locator(".activity")
            .getByText("Menunggu approval", { exact: true }),
    ).toBeVisible();
    await openExpenses(page);
    await page
        .getByRole("button", { name: "Simulasikan approval & pencairan" })
        .click();
    await expect(
        page.getByText("Uang muka fiktif Rp", { exact: false }),
    ).toBeVisible();
}
async function openExpenses(page: Page) {
    await page
        .getByRole("button", { name: "Realisasi & saldo uang lapangan" })
        .click();
    await page.getByRole("button", { name: /Petty cash/ }).click();
}
async function details(page: Page, n: number, amount: string, receipt: string) {
    await page
        .getByLabel(`Uraian biaya ${n}`, { exact: true })
        .fill("Biaya perjalanan demo");
    await page
        .getByLabel(`Nominal realisasi ${n} (Rp)`, { exact: true })
        .fill(amount);
    await page
        .getByLabel(`Nama penjual ${n}`, { exact: true })
        .fill("Penjual simulasi");
    await page.getByLabel(`Nomor struk ${n}`, { exact: true }).fill(receipt);
}
async function photo(page: Page, context: BrowserContext, name: string) {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({
        latitude: 1.465,
        longitude: 124.833,
        accuracy: 3,
    });
    const group = page.getByRole("group", { name, exact: true });
    await group.getByLabel("Foto bukti").setInputFiles("public/icon-192.png");
    await expect(
        group.getByAltText("Pratinjau foto bukti lokal"),
    ).toBeVisible();
    await group.getByRole("button", { name: "Ambil lokasi sekarang" }).click();
    await group.getByRole("button", { name: "Simpan bukti lokal" }).click();
    await expect(
        group.getByText("Bukti lokal tersimpan", { exact: false }),
    ).toBeVisible();
}
test("component draft restores offline and queues realization separately from approval/settlement", async ({
    page,
    context,
}) => {
    await requestAdvance(page);
    await details(page, 1, "100000", "MEAL-001");
    await photo(page, context, "Foto struk 1");
    await page.getByRole("button", { name: "Tambah komponen biaya" }).click();
    await details(page, 2, "50000", "MEAL-002");
    await photo(page, context, "Foto struk 2");
    await expect(
        page.getByRole("region", { name: "Estimasi settlement" }),
    ).toContainText(/Rp\s*150\.000/);
    await expect(
        page.getByText("Draft tersimpan di perangkat.", { exact: true }),
    ).toBeVisible();
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await openExpenses(page);
    await expect(
        page.getByLabel("Nominal realisasi 2 (Rp)", { exact: true }),
    ).toHaveValue("50000");
    await expect(page.getByAltText("Pratinjau foto bukti lokal")).toHaveCount(
        2,
    );
    await expect(
        page.getByRole("region", { name: "Estimasi settlement" }),
    ).toContainText(/Rp\s*50\.000/);
    await page
        .getByRole("button", { name: "Simpan realisasi ke antrean demo" })
        .click();
    await expect(
        page.locator(".realization-form > .notice[role=status]"),
    ).toContainText("Menunggu koneksi");
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await openExpenses(page);
    await expect(
        page.getByLabel("Nominal realisasi 1 (Rp)", { exact: true }),
    ).toBeDisabled();
    await context.setOffline(false);
    await expect(
        page.locator(".realization-form > .notice[role=status]"),
    ).toContainText("Menunggu approval", { timeout: 20000 });
    await expect(
        page.getByText("Saldo belum final.", { exact: false }),
    ).toBeVisible();
    await page.screenshot({
        path: `test-results/expense-${test.info().project.name}.png`,
        fullPage: true,
    });
    await page.getByRole("button", { name: "Kembali ke akun" }).click();
    await page.getByLabel("Persona demo").selectOption("delivery");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await page
        .getByRole("button", { name: "Realisasi & saldo uang lapangan" })
        .click();
    await expect(
        page.getByText("Belum ada pengajuan biaya pada akun ini."),
    ).toBeVisible();
});
test("fuel validates paired local evidence, liter-price arithmetic and nondecreasing odometer", async ({
    page,
    context,
}) => {
    await requestAdvance(page, "fuel_emergency");
    await details(page, 1, "150000", "FUEL-001");
    await photo(page, context, "Foto struk 1");
    await page.getByLabel("Liter BBM", { exact: true }).fill("14");
    await page
        .getByLabel("Harga per liter (Rp)", { exact: true })
        .fill("10000");
    await page.getByLabel("KM sebelum pengisian", { exact: true }).fill("1000");
    await page.getByLabel("KM setelah pengisian", { exact: true }).fill("999");
    await photo(page, context, "Foto odometer sebelum");
    await photo(page, context, "Foto odometer sesudah");
    await page
        .getByRole("button", { name: "Simpan realisasi ke antrean demo" })
        .click();
    await expect(page.getByRole("alert")).toContainText("liter × harga");
    await page.getByLabel("Liter BBM", { exact: true }).fill("15");
    await page
        .getByRole("button", { name: "Simpan realisasi ke antrean demo" })
        .click();
    await expect(page.getByRole("alert")).toContainText("KM tidak boleh turun");
    await page.getByLabel("KM setelah pengisian", { exact: true }).fill("1000");
    await expect(
        page.getByRole("region", { name: "Estimasi settlement" }),
    ).toContainText("Supervisor + Branch Manager");
    await page
        .getByRole("button", { name: "Simpan realisasi ke antrean demo" })
        .click();
    await expect(
        page.locator(".realization-form > .notice[role=status]"),
    ).toContainText("Menunggu approval");
    expect(
        await page.evaluate(async () => {
            const db = await new Promise<IDBDatabase>((resolve) => {
                const r = indexedDB.open("fmcg-field-demo-v1");
                r.onsuccess = () => resolve(r.result);
            });
            const tx = db.transaction("outbox", "readonly");
            const rows = await new Promise<unknown[]>((resolve) => {
                const r = tx.objectStore("outbox").getAll();
                r.onsuccess = () => resolve(r.result);
            });
            db.close();
            const payload = (
                rows as {
                    command: {
                        type: string;
                        payload: {
                            lines: { evidence: { id: string } }[];
                            fuel: {
                                before: { id: string };
                                after: { id: string };
                            };
                            evidence_status: string;
                        };
                    };
                }[]
            ).find(
                (q) => q.command.type === "field_expense.realization.submit",
            )!.command.payload;
            return {
                distinct: new Set([
                    payload.lines[0].evidence.id,
                    payload.fuel.before.id,
                    payload.fuel.after.id,
                ]).size,
                status: payload.evidence_status,
            };
        }),
    ).toEqual({ distinct: 3, status: "local_map_pending" });
});

test("photo previews follow stable components after removal and clear when a replacement is invalid", async ({
    page,
    context,
}) => {
    await requestAdvance(page);
    await details(page, 1, "50000", "PHOTO-A");
    await photo(page, context, "Foto struk 1");
    await page.getByRole("button", { name: "Tambah komponen biaya" }).click();
    await details(page, 2, "60000", "PHOTO-B");
    await photo(page, context, "Foto struk 2");
    const secondSrc = await page
        .getByRole("group", { name: "Foto struk 2", exact: true })
        .getByAltText("Pratinjau foto bukti lokal")
        .getAttribute("src");
    await page
        .getByRole("button", { name: "Hapus komponen 1", exact: true })
        .click();
    await expect(page.getByLabel("Nomor struk 1", { exact: true })).toHaveValue(
        "PHOTO-B",
    );
    const remaining = page.getByRole("group", {
        name: "Foto struk 1",
        exact: true,
    });
    await expect(
        remaining.getByAltText("Pratinjau foto bukti lokal"),
    ).toHaveAttribute("src", secondSrc!);
    await remaining.getByLabel("Foto bukti").setInputFiles({
        name: "invalid.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("invalid replacement"),
    });
    await expect(
        remaining.getByText("Pilih JPEG", { exact: false }),
    ).toBeVisible();
    await expect(
        remaining.getByAltText("Pratinjau foto bukti lokal"),
    ).toHaveCount(0);
    await expect(remaining.locator(".coordinates")).toHaveCount(0);
    await page.getByRole("button", { name: "Tambah komponen biaya" }).click();
    await expect(
        page
            .getByRole("group", { name: "Foto struk 2", exact: true })
            .getByAltText("Pratinjau foto bukti lokal"),
    ).toHaveCount(0);
});
test("missing persisted photo clears the preview and blocks realization without erasing the draft", async ({
    page,
    context,
}) => {
    await requestAdvance(page);
    await details(page, 1, "100000", "MISSING-PHOTO");
    await photo(page, context, "Foto struk 1");
    await expect(
        page.getByText("Draft tersimpan di perangkat.", { exact: true }),
    ).toBeVisible();
    await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const tx = db.transaction("evidence", "readwrite");
        tx.objectStore("evidence").clear();
        await new Promise<void>((resolve, reject) => {
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
        db.close();
    });
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await openExpenses(page);
    const group = page.getByRole("group", {
        name: "Foto struk 1",
        exact: true,
    });
    await expect(
        group.getByText("Foto lokal tidak dapat dipulihkan.", { exact: false }),
    ).toBeVisible();
    await expect(group.getByAltText("Pratinjau foto bukti lokal")).toHaveCount(
        0,
    );
    await page
        .getByRole("button", { name: "Simpan realisasi ke antrean demo" })
        .click();
    await expect(page.getByRole("alert")).toContainText(
        "Foto lokal tidak ditemukan",
    );
    await expect(page.getByLabel("Nomor struk 1", { exact: true })).toHaveValue(
        "MISSING-PHOTO",
    );
});
test("business rejection opens an auditable correction with a new UUID, leaving the rejected command unchanged", async ({
    page,
    context,
}) => {
    await requestAdvance(page);
    await details(page, 1, "150000", "REVISION-001");
    await photo(page, context, "Foto struk 1");
    await page.getByRole("button", { name: "Kembali ke akun" }).click();
    await page.getByLabel("Respons simulator").selectOption("rejected");
    await openExpenses(page);
    await page
        .getByRole("button", { name: "Simpan realisasi ke antrean demo" })
        .click();
    await expect(
        page.getByRole("heading", { name: "Koreksi realisasi ditolak" }),
    ).toBeVisible();
    const previous = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const rows = await new Promise<
            {
                command: {
                    type: string;
                    client_uuid: string;
                    payload: unknown;
                };
            }[]
        >((resolve) => {
            const r = db.transaction("outbox").objectStore("outbox").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        db.close();
        return rows.find(
            (q) => q.command.type === "field_expense.realization.submit",
        )!;
    });
    await page
        .getByLabel("Nominal realisasi 1 (Rp)", { exact: true })
        .fill("140000");
    await page
        .getByLabel("Alasan koreksi", { exact: true })
        .fill("Perbaikan nominal sesuai struk");
    await page.getByRole("button", { name: "Kembali ke akun" }).click();
    await page.getByLabel("Respons simulator").selectOption("normal");
    await openExpenses(page);
    await expect(
        page.getByLabel("Alasan koreksi", { exact: true }),
    ).toHaveValue("Perbaikan nominal sesuai struk");
    await page
        .getByRole("button", { name: "Simpan realisasi ke antrean demo" })
        .click();
    await expect(
        page.locator(".realization-form > .notice[role=status]"),
    ).toContainText("Menunggu approval");
    await expect(
        page.getByRole("region", { name: "Riwayat realisasi" }),
    ).toContainText("koreksi");
    const rows = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const values = await new Promise<
            {
                command: {
                    type: string;
                    client_uuid: string;
                    payload: {
                        supersedes_uuid?: string;
                        correction_reason?: string;
                    };
                };
            }[]
        >((resolve) => {
            const r = db.transaction("outbox").objectStore("outbox").getAll();
            r.onsuccess = () => resolve(r.result);
        });
        db.close();
        return values.filter(
            (q) => q.command.type === "field_expense.realization.submit",
        );
    });
    expect(rows).toHaveLength(2);
    expect(
        rows.find(
            (q) => q.command.client_uuid === previous.command.client_uuid,
        ),
    ).toEqual(previous);
    expect(
        rows.find((q) => q.command.client_uuid !== previous.command.client_uuid)
            ?.command.payload,
    ).toMatchObject({
        supersedes_uuid: previous.command.client_uuid,
        correction_reason: "Perbaikan nominal sesuai struk",
    });
    await expect(
        page.getByLabel("Nominal realisasi 1 (Rp)", { exact: true }),
    ).toBeDisabled();
});
