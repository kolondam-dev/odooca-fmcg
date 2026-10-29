import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
    testDir: "./tests/browser",
    fullyParallel: true,
    retries: process.env.CI ? 1 : 0,
    reporter: [["list"], ["html", { open: "never" }]],
    use: {
        launchOptions: {
            ...(process.env.PWA_CHROMIUM_EXECUTABLE
                ? {
                      executablePath: process.env.PWA_CHROMIUM_EXECUTABLE,
                      args: [
                          "--no-sandbox",
                          "--disable-dev-shm-usage",
                          "--disable-gpu",
                      ],
                  }
                : {}),
        },
        baseURL: "http://127.0.0.1:4173/field/",
        trace: "retain-on-failure",
        screenshot: "only-on-failure",
    },
    projects: [
        { name: "phone", use: { ...devices["Pixel 5"] } },
        { name: "tablet", use: { viewport: { width: 1024, height: 768 } } },
    ],
    webServer: [
        {
            command: "npm start",
            env: { PORT: "4173", PWA_DIST: "dist/demo" },
            port: 4173,
            reuseExistingServer: !process.env.CI,
        },
        {
            command: "npm start",
            env: { PORT: "4174", PWA_DIST: "dist/live" },
            port: 4174,
            reuseExistingServer: !process.env.CI,
        },
        {
            command: "npm start",
            env: { PORT: "4175", PWA_DIST: "dist/staging" },
            port: 4175,
            reuseExistingServer: !process.env.CI,
        },
    ],
});
