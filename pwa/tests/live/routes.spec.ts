import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { evidenceName, publicOnly, targetUrl } from "./helpers";

type EvidenceRoute = {
    name: string;
    target: "odoo" | "pwa";
    path: string;
    expectText?: string;
};

const routeFile = process.env.LIVE_UI_ROUTE_FILE;

test("@routes capture configured read-only evidence routes", async ({
    page,
}, testInfo) => {
    test.skip(publicOnly, "Evidence routes require an authenticated session");
    test.skip(!routeFile, "LIVE_UI_ROUTE_FILE is not configured");
    const contents = await readFile(routeFile!, "utf8");
    const routes = JSON.parse(
        contents.replace(/^\uFEFF/, ""),
    ) as EvidenceRoute[];
    expect(routes.length).toBeGreaterThan(0);

    for (const route of routes) {
        const response = await page.goto(targetUrl(route.target, route.path), {
            waitUntil: "domcontentloaded",
        });
        expect(response?.status(), route.name).toBeLessThan(400);
        if (route.expectText) {
            await expect(
                page.getByText(route.expectText).first(),
            ).toBeVisible();
        }
        await page.screenshot({
            path: evidenceName(testInfo, route.name),
            fullPage: true,
        });
    }
});
