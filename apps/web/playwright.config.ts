import { defineConfig, devices } from "@playwright/test";

const origin = process.env.UI_ORIGIN ?? "http://localhost:3100";
const port = new URL(origin).port || "80";

export default defineConfig({
    testDir: "./tests",
    fullyParallel: false,
    workers: 1,
    use: { baseURL: origin, trace: "retain-on-failure" },
    webServer: {
        command: `npm run start -- -p ${port}`,
        url: origin,
        reuseExistingServer: false,
        env: { API_URL: process.env.API_URL ?? "http://localhost:8000", UI_ORIGIN: origin, MINIO_PUBLIC_ORIGIN: process.env.MINIO_PUBLIC_ORIGIN ?? "http://localhost:9000" },
    },
    projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
