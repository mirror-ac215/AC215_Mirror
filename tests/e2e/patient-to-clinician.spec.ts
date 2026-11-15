import { expect, test, type Page } from "@playwright/test";

const demoPassword = process.env.MIRROR_DEMO_PASSWORD;

if (!demoPassword) {
  throw new Error("MIRROR_DEMO_PASSWORD must be set for the seeded Compose test accounts.");
}

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(demoPassword!);
  await page.getByRole("button", { name: "Continue" }).click();
}

test("patient consent, fake-camera chat, and assigned clinician view", async ({ page }) => {
  await signIn(page, "patient.alex@example.test");
  await expect(page).toHaveURL(/\/consent$/);
  await page.getByRole("button", { name: "Start session" }).click();

  await expect(page).toHaveURL(/\/session\?camera=true$/);
  await expect(page.getByRole("button", { name: "Turn camera off" })).toBeVisible();
  await expect(page.getByText("Today's check-in")).toBeVisible();

  await page.getByPlaceholder("Type a message…").fill("I am checking in through the smoke test.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("I am checking in through the smoke test.")).toBeVisible();
  await expect(
    page.getByText("That sounds like a lot to carry. What feels most pressing right now?"),
  ).toBeVisible();

  await page.getByRole("button", { name: /Signed in/ }).click();
  await page.getByRole("menuitem", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);

  await signIn(page, "clinician.ada@example.test");
  await expect(page).toHaveURL(/\/clinician\/?$/);
  await expect(page.getByRole("heading", { name: "Your patients" })).toBeVisible();
  await expect(page.getByText("Alex Rivera")).toBeVisible();
  await expect(page.getByText("Bri Santos")).toBeVisible();

  await page.getByRole("link", { name: /Alex Rivera/ }).click();
  await expect(page).toHaveURL(/\/clinician\/00000000-0000-0000-0000-000000000201$/);
  await expect(page.getByRole("heading", { name: "Alex Rivera" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review queue" })).toBeVisible();
});
