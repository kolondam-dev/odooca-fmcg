import { defineConfig, devices } from "@playwright/test";

const yes = (value: string | undefined) => value?.toUpperCase() === "YES";
const publicOnly = yes(process.env.LIVE_UI_PUBLIC_ONLY);
const timeout = Number(process.env.LIVE_UI_TIMEOUT_MS ?? "60000");

if (!process.env.LIVE_UI_ODOO_URL && !process.env.LIVE_UI_PWA_URL) {
    throw new Error(
        "Set LIVE_UI_ODOO_URL and/or LIVE_UI_PWA_URL in pwa/.env.live-ui.local.",
    );
}
if (
    !publicOnly &&
    !(process.env.ODOO_DEMO_LOGIN && process.env.ODOO_DEMO_PASSWORD)
) {
    throw new Error(
        "Set ODOO_DEMO_LOGIN and ODOO_DEMO_PASSWORD, or use LIVE_UI_PUBLIC_ONLY=YES.",
    );
}

const authenticatedUse = publicOnly
    ? {}
    : { storageState: "test-results/live-ui/.auth/state.json" };
const browserProjects = [
    {
        name: "live-desktop",
        use: { ...devices["Desktop Chrome"], ...authenticatedUse },
        dependencies: publicOnly ? [] : ["live-auth"],
    },
    {
        name: "live-phone",
        use: { ...devices["Pixel 5"], ...authenticatedUse },
        dependencies: publicOnly ? [] : ["live-auth"],
    },
];

export default defineConfig({
    testDir: "./tests",
    testMatch: ["live/**/*.spec.ts", "live-local/**/*.spec.ts"],
    testIgnore: ["**/auth.setup.ts"],
    fullyParallel: false,
    workers: Number(process.env.LIVE_UI_WORKERS ?? "1"),
    retries: 0,
    timeout,
    expect: { timeout: Math.min(timeout, 15000) },
    outputDir: "test-results/live-ui",
    reporter: [
        ["list"],
        ["html", { outputFolder: "playwright-report/live-ui", open: "never" }],
    ],
    use: {
        headless: true,
        ignoreHTTPSErrors: yes(process.env.LIVE_UI_IGNORE_HTTPS_ERRORS),
        actionTimeout: Math.min(timeout, 15000),
        navigationTimeout: timeout,
        screenshot: "only-on-failure",
        trace: yes(process.env.LIVE_UI_TRACE) ? "retain-on-failure" : "off",
        video: "off",
        launchOptions: process.env.LIVE_UI_CHROMIUM_EXECUTABLE
            ? { executablePath: process.env.LIVE_UI_CHROMIUM_EXECUTABLE }
            : {},
    },
    projects: publicOnly
        ? browserProjects
        : [
              {
                  name: "live-auth",
                  testMatch: "live/auth.setup.ts",
                  testIgnore: [],
                  use: { ...devices["Desktop Chrome"] },
              },
              ...browserProjects,
          ],
});
