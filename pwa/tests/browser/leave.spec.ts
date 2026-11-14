import { expect, test } from "./session-fixture";
import { activity, openActivity } from "./visit-helpers";

test("Ajukan cuti: validasi, durasi hari kerja, dan pengajuan masuk antrean sebagai hris.leave.request", async ({
    page,
}) => {
    await page.goto("./");
    await page.getByRole("button", { name: "HRIS", exact: true }).click();
    await page.getByRole("button", { name: /Pengajuan cuti/ }).click();
    const screen = page.getByRole("region", { name: "Ajukan cuti" });
    await screen.getByRole("button", { name: "Kirim pengajuan" }).click();
    await expect(screen.getByRole("alert")).toContainText("wajib diisi");
    await screen.getByLabel(/^Mulai/).fill("2026-11-12");
    await screen.getByLabel(/^Selesai/).fill("2026-11-11");
    await screen.getByLabel("Alasan").fill("Acara keluarga");
    await screen.getByRole("button", { name: "Kirim pengajuan" }).click();
    await expect(screen.getByRole("alert")).toContainText("sebelum mulai");
    await screen.getByLabel(/^Selesai/).fill("2026-11-13");
    await expect(screen.getByText("2 hari kerja")).toBeVisible();
    await screen.getByRole("button", { name: "Kirim pengajuan" }).click();
    await expect(screen).toHaveCount(0);
    const types = await page.evaluate(async () => {
        const db = await new Promise<IDBDatabase>((resolve) => {
            const r = indexedDB.open("fmcg-field-demo-v1");
            r.onsuccess = () => resolve(r.result);
        });
        const rows = await new Promise<
            Array<{ command: { type: string; payload: unknown } }>
        >((resolve) => {
            const g = db
                .transaction("outbox", "readonly")
                .objectStore("outbox")
                .getAll();
            g.onsuccess = () => resolve(g.result);
        });
        db.close();
        return rows.map((r) => r.command);
    });
    const leave = types.find((c) => c.type === "hris.leave.request");
    expect(leave?.payload).toEqual({
        date_from: "2026-11-12",
        date_to: "2026-11-13",
        reason: "Acara keluarga",
    });
    await page.getByRole("button", { name: "Lainnya", exact: true }).click();
    await openActivity(page);
    await expect(activity(page).getByText(/Pengajuan cuti/)).toBeVisible();
});
