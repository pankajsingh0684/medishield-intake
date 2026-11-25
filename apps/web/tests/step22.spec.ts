import { expect, Page, test } from "@playwright/test";
import path from "node:path";

const password = process.env.SEED_TEST_USER_PASSWORD;

async function login(page: Page, email: string) {
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password!);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL("/");
}

test.beforeAll(() => {
    if (!password) throw new Error("SEED_TEST_USER_PASSWORD is required");
});

test("review override preserves original decision and writes an audit event", async ({ page }) => {
    await login(page, "reviewer@medishield.test");
    await page.goto("/review");
    const queueResponse = await page.request.get("/api/backend/review-queue?page_size=100");
    expect(queueResponse.ok()).toBeTruthy();
    const queue = await queueResponse.json();
    let escalated = queue.items.find((item: { original_decision: { decision: string } | null; overrides: unknown[] }) => item.original_decision?.decision === "ESCALATE" && item.overrides.length === 0);
    for (let pageNumber = 2; !escalated && (pageNumber - 1) * 100 < queue.total; pageNumber += 1) {
        const next = await (await page.request.get(`/api/backend/review-queue?page=${pageNumber}&page_size=100`)).json();
        escalated = next.items.find((item: { original_decision: { decision: string } | null; overrides: unknown[] }) => item.original_decision?.decision === "ESCALATE" && item.overrides.length === 0);
    }
    expect(escalated).toBeTruthy();
    const href = `/cases/${escalated.case_id}`;
    await page.goto(href);
    await page.getByRole("button", { name: "Review action" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Action").selectOption("APPROVE");
    await dialog.getByLabel("Reason").fill("Playwright approved after manual review");
    await dialog.getByRole("button", { name: "Submit action" }).click();
    await page.goto(href!);
    await expect(page.getByText("OVERRIDDEN", { exact: true })).toBeVisible();
    await expect(page.getByText("Original", { exact: true })).toBeVisible();
    await expect(page.getByText("Effective", { exact: true })).toBeVisible();
    await expect(page.getByText("APPROVE", { exact: true }).first()).toBeVisible();
    await page.getByRole("tab", { name: "Audit log" }).click();
    await expect(page.getByText("OVERRIDE", { exact: true })).toBeVisible();
});

test("auditor cannot see review actions", async ({ page }) => {
    await login(page, "auditor@medishield.test");
    const caseLink = page.locator("table tbody tr").first().getByRole("link");
    await expect(caseLink).toBeVisible();
    await caseLink.click();
    await expect(page.getByRole("button", { name: "Review action" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Rerun pipeline" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Review", exact: true })).toHaveCount(0);
});

test("supervisor can upload a policy and see ingestion status", async ({ page }) => {
    await login(page, "supervisor@medishield.test");
    await page.goto("/policies");
    await page.getByLabel("Name").fill("MediShield Gold Plan");
    await page.getByLabel("Version").fill(`e2e-${Date.now()}`);
    await page.getByLabel("Effective from").fill("2026-01-01");
    await page.getByLabel("PDF").setInputFiles(path.resolve(__dirname, "../../../data/synthetic/policy/medishield_gold_plan.pdf"));
    await page.getByRole("button", { name: "Upload policy" }).click();
    await expect(page.getByText(/PENDING|PROCESSING|READY|FAILED|COMPLETED/, { exact: true }).first()).toBeVisible();
});
