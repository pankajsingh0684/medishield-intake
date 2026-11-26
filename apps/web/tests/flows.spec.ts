import { expect, test } from "@playwright/test";

const email = process.env.SEED_TEST_USER_EMAIL ?? "reviewer@medishield.test";
const password = process.env.SEED_TEST_USER_PASSWORD;

test.beforeAll(() => {
    if (!password) throw new Error("SEED_TEST_USER_PASSWORD is required");
});

test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password!);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL("/");
});

test("login is protected by an httpOnly cookie and loads the dashboard", async ({ page, context }) => {
    const cookies = await context.cookies();
    const token = cookies.find((cookie) => cookie.name === "medishield_token");
    expect(token?.httpOnly).toBeTruthy();
    expect(token?.sameSite).toBe("Lax");
    await expect(page.getByRole("heading", { name: "MediShield cases" })).toBeVisible();
    await expect(page.getByText(/cases$/).last()).toBeVisible();
});

test("dashboard loads seeded cases and case detail opens", async ({ page }) => {
    const firstCase = page.locator("table tbody tr").first().getByRole("link");
    await expect(firstCase).toBeVisible();
    await firstCase.click();
    await expect(page.getByRole("heading", { name: "Decision" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Document viewer" })).toBeVisible();
    await expect(page.getByText("Agent outputs", { exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "Audit log" }).click();
    await expect(page.getByRole("tab", { name: "Audit log" })).toHaveAttribute("aria-selected", "true");
});

test("login and inaccessible sessions show usable errors", async ({ page }) => {
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL("/login");
    await page.goto("/cases/not-a-case");
    await expect(page).toHaveURL("/login");
});

test("dashboard aggregate cards are non-zero after seeding", async ({ page }) => {
    await expect(page.getByRole("link", { name: /Processing/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Approved/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Rejected/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Escalated/i })).toBeVisible();
    await expect.poll(async () => {
        const counts = await page.locator("section[aria-label='Case status counts'] .text-3xl").allTextContents();
        return counts.some((count) => Number(count) > 0);
    }).toBeTruthy();
    await page.getByRole("link", { name: /Approved/i }).click();
    await expect(page).toHaveURL(/card=approved/);
});
