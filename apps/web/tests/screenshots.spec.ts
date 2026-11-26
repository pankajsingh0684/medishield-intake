import { expect, test } from "@playwright/test";
import path from "node:path";

test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });

test("capture seeded application views", async ({ page }) => {
    const password = process.env.SEED_TEST_USER_PASSWORD;
    if (!password) throw new Error("SEED_TEST_USER_PASSWORD is required");
    const screenshot = (name: string) => page.screenshot({ path: path.resolve("../../docs/screenshots", `${name}.png`), fullPage: true });
    await page.goto("/login");
    await screenshot("login");
    await page.getByLabel("Email").fill(process.env.SEED_TEST_USER_EMAIL ?? "reviewer@medishield.test");
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("link", { name: /Approved/i })).toBeVisible();
    const stats = await page.request.get("/api/cases/stats");
    expect(stats.ok()).toBeTruthy();
    console.log("Dashboard counts:", JSON.stringify(await stats.json()));
    await screenshot("dashboard");
    await page.getByRole("link", { name: /Approved/i }).click();
    await expect(page).toHaveURL(/card=approved/);
    await expect(page.locator("table tbody tr").first()).toBeVisible();
    await screenshot("case-list");
    await page.locator("table tbody tr").first().getByRole("link").click();
    await expect(page.getByRole("region", { name: "Document viewer" })).toBeVisible();
    await screenshot("case-detail");
    await page.goto("/policies");
    await expect(page.getByRole("heading", { name: /polic/i }).first()).toBeVisible();
    await screenshot("policies");
});