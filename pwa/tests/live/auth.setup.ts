import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { test as setup } from "@playwright/test";
import { loginThroughForm, odooBase } from "./helpers";

const statePath = "test-results/live-ui/.auth/state.json";

setup(
    "@smoke @odoo-live @pwa-live @routes authenticate reusable context",
    async ({ page }) => {
        if (!odooBase) {
            throw new Error(
                "Authenticated setup requires LIVE_UI_ODOO_URL, preferably the same-origin gateway used by the PWA.",
            );
        }
        const loginUrl = new URL("web/login", odooBase).href;
        await loginThroughForm(page, `${loginUrl}?redirect=%2Fodoo`);
        await mkdir(dirname(statePath), { recursive: true });
        await page.context().storageState({ path: statePath });
    },
);
