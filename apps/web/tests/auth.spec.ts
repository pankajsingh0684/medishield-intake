import { expect, test } from "@playwright/test";

test("invalid login displays an accessible error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("invalid@medishield.test");
    await page.getByLabel("Password").fill("invalid-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
});
