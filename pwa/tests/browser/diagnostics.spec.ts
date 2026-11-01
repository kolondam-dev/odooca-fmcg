import { switchPersona } from "./delivery-helpers";
import { expect, test } from "./session-fixture";
test("diagnosis filters, safe detail and persona isolation preserve offline data", async ({
    page,
    context,
}) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("./");
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    await context.setOffline(true);
    const ids = await page.evaluate(async () => {
        const owner = "demo-mdu:DEMO-ANDRE";
        const db = await new Promise<IDBDatabase>((resolve, reject) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
            r.onerror = () => reject(r.error);
        });
        const states = [
            "queued",
            "accepted",
            "needs_approval",
            "rejected",
            "auth_required",
            "queued",
        ];
        const rows = states.map((state, i) => {
            const id = crypto.randomUUID();
            return {
                key: `${owner}:${id}`,
                owner,
                label: `Diagnostic fixture ${i}`,
                state,
                attempts: 0,
                nextAttempt: 0,
                command:
                    i === 5
                        ? null
                        : {
                              schema_version: 1,
                              client_uuid: id,
                              type: "field_expense.request",
                              occurred_at: new Date().toISOString(),
                              payload: {
                                  note: "SECRET-PAYLOAD-NOT-DISPLAYED",
                                  token: "SECRET-TOKEN-NOT-DISPLAYED",
                              },
                          },
                ...(["accepted", "needs_approval"].includes(state)
                    ? {
                          receipt: {
                              client_uuid: id,
                              status: state,
                              message: "Receipt simulator",
                              reference: `SIM-DIAG-${i}`,
                          },
                      }
                    : {}),
            };
        });
        const tx = db.transaction("outbox", "readwrite");
        for (const row of rows) tx.objectStore("outbox").put(row);
        await new Promise<void>((resolve, reject) => {
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
        });
        db.close();
        return rows.map((r) => r.key.split(":").at(-1)!);
    });
    await page.reload();
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    const region = page.getByRole("region", {
        name: "Diagnosis sinkronisasi",
        exact: true,
    });
    await expect(region.locator(".activity")).toHaveCount(6);
    await expect(region).not.toContainText("SECRET-PAYLOAD-NOT-DISPLAYED");
    await expect(region).not.toContainText("SECRET-TOKEN-NOT-DISPLAYED");
    const before = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const tx = db.transaction(["drafts", "outbox"], "readonly");
        const rows = await Promise.all(
            ["drafts", "outbox"].map(
                (name) =>
                    new Promise((resolve) => {
                        const r = tx.objectStore(name).getAll();
                        r.onsuccess = () => resolve(r.result);
                    }),
            ),
        );
        db.close();
        return rows;
    });
    await region
        .getByRole("button", { name: "Perlu review 3", exact: true })
        .click();
    await expect(region.locator(".activity")).toHaveCount(3);
    const auth = region
        .locator(".activity")
        .filter({ hasText: "Diagnostic fixture 4" });
    await auth.getByText("Detail sinkronisasi", { exact: true }).click();
    await expect(auth.getByText(ids[4], { exact: true })).toBeVisible();
    await expect(auth).toContainText(
        "Sinkronkan tidak memulihkan sesi yang habis",
    );
    await region
        .getByRole("button", { name: "Approval 1", exact: true })
        .click();
    await expect(region.locator(".activity")).toHaveCount(1);
    await region.getByText("Detail sinkronisasi", { exact: true }).click();
    await expect(region).toContainText(
        "Belum disetujui, dicairkan atau diposting ke Odoo",
    );
    await region
        .getByRole("button", { name: "Diterima 1", exact: true })
        .click();
    await expect(region.locator(".activity")).toHaveCount(1);
    await region
        .getByRole("button", { name: "Menunggu 1", exact: true })
        .click();
    await expect(region.locator(".activity")).toHaveCount(1);
    await region.getByText("Detail sinkronisasi", { exact: true }).click();
    await expect(region).toContainText("Tersimpan saat offline");
    expect(
        await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
        ),
    ).toBe(true);
    await page.screenshot({
        path: `test-results/diagnosis-${test.info().project.name}.png`,
        fullPage: true,
    });
    await switchPersona(page, "delivery");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(
        page.getByText(
            "Belum ada aktivitas. Mulai dari order atau pengajuan.",
            { exact: true },
        ),
    ).toBeVisible();
    await expect(
        page.getByText("Diagnostic fixture 4", { exact: true }),
    ).toHaveCount(0);
    await switchPersona(page, "sales");
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await expect(region.locator(".activity")).toHaveCount(6);
    const after = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const tx = db.transaction(["drafts", "outbox"], "readonly");
        const rows = await Promise.all(
            ["drafts", "outbox"].map(
                (name) =>
                    new Promise((resolve) => {
                        const r = tx.objectStore(name).getAll();
                        r.onsuccess = () => resolve(r.result);
                    }),
            ),
        );
        db.close();
        return rows;
    });
    expect(after).toEqual(before);
    expect(errors).toEqual([]);
});
