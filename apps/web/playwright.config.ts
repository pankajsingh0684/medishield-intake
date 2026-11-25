import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
    testDir: "./tests",
    fullyParallel: false,
    workers: 1,
    use: { baseURL: process.env.UI_ORIGIN ?? "http://localhost:3000", trace: "retain-on-failure" },
    webServer: {
        command: "npm run dev",
        url: process.env.UI_ORIGIN ?? "http://localhost:3000",
        reuseExistingServer: true,
        env: { API_URL: process.env.API_URL ?? "http://localhost:8000", UI_ORIGIN: process.env.UI_ORIGIN ?? "http://localhost:3000", MINIO_PUBLIC_ORIGIN: process.env.MINIO_PUBLIC_ORIGIN ?? "http://localhost:9000" },
    },
    projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
