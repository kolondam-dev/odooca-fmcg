import { changeTestAccount, checkIn } from "./session-fixture";
import { expect, type Locator, type Page } from "@playwright/test";
const owners = {
    sales: "demo-mdu:DEMO-ANDRE",
    delivery: "demo-mdu:DEMO-NOVRY",
    canvass: "demo-mdu:DEMO-STEVEN",
};
export async function switchPersona(page: Page, actor: keyof typeof owners) {
    await changeTestAccount(page, actor);
    await page.getByRole("button", { name: "Beranda", exact: true }).click();
    const region = page.getByRole("region", {
        name: "Sesi kerja",
        exact: true,
    });
    await expect(region).toHaveAttribute("data-owner", owners[actor]);
    await expect(region).toHaveAttribute("aria-busy", "false");
}
export async function ensureDaily(page: Page) {
    await page.getByRole("button", { name: "Beranda", exact: true }).click();
    await checkIn(page);
    const region = page.getByRole("region", {
        name: "Sesi kerja",
        exact: true,
    });
    await expect(region).toHaveAttribute("aria-busy", "false");
    const ready = region.getByText("Sesi aktif", { exact: true });
    if (await ready.isVisible()) return;
    const open = region.getByRole("button", {
        name: "Buka sesi kerja",
        exact: true,
    });
    await expect(open).toBeEnabled();
    await open.click();
    await expect(region).toHaveAttribute("aria-busy", "false");
    await expect(ready).toBeVisible();
}
export async function saveDeliveryPhoto(task: Locator) {
    const preview = task.getByRole("button", {
        name: "Preview penerimaan",
        exact: true,
    });
    if (await preview.isVisible())
        await task.getByRole("button", { name: /^Tutup / }).click();
    const close = task.getByRole("button", {
        name: "Close session",
        exact: true,
    });
    if (
        !(await task
            .getByRole("button", { name: "Mulai sesi delivery", exact: true })
            .isVisible()) &&
        (await close.isEnabled())
    )
        await close.click();
    await task.getByLabel("Foto bukti").setInputFiles("public/icon-192.png");
    await expect(task.getByAltText("Pratinjau foto bukti lokal")).toBeVisible();
    await task
        .getByRole("button", { name: "Ambil lokasi sekarang", exact: true })
        .click();
    await task
        .getByRole("button", { name: "Simpan bukti lokal", exact: true })
        .click();
    await expect(task.getByText("Foto dan lokasi tersimpan.")).toBeVisible();
}
export async function startDelivery(task: Locator) {
    await expect(task).toHaveAttribute("aria-busy", "false");
    if (
        await task
            .getByRole("button", { name: "Mulai sesi delivery", exact: true })
            .isVisible()
    ) {
        await saveDeliveryPhoto(task);
        await task
            .getByRole("button", {
                name: "Perbarui lokasi delivery",
                exact: true,
            })
            .click();
        await task
            .getByRole("button", { name: "Mulai sesi delivery", exact: true })
            .click();
        await task
            .getByRole("button", { name: "Open session", exact: true })
            .click();
        await expect(task.getByText(/Sesi delivery aktif/)).toBeVisible();
        await task
            .getByLabel("Alasan status (direkam ke semua item)", {
                exact: true,
            })
            .fill("Diterima sesuai dokumen");
    }
    const open = task.getByRole("button", {
        name: "Open session",
        exact: true,
    });
    if (
        !(await task.getByRole("dialog").isVisible()) &&
        (await open.isEnabled())
    )
        await open.click();
    const reason = task.getByLabel("Alasan status (direkam ke semua item)", {
        exact: true,
    });
    if ((await reason.isVisible()) && !(await reason.inputValue()))
        await reason.fill("Diterima sesuai dokumen");
}
