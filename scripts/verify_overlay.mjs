import { build } from "esbuild";
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import assert from "node:assert/strict";

const root = fileURLToPath(new URL("..", import.meta.url));
await mkdir(path.join(root, ".cache"), { recursive: true });
await build({
  entryPoints: [path.join(root, "tests/overlay-harness.tsx")], bundle: true, jsx: "automatic",
  outfile: path.join(root, ".cache/overlay-preview.js"),
  plugins: [{ name: "decky-test-shim", setup(builder) {
    builder.onResolve({ filter: /^@decky\/(ui|api)$/ }, (args) => ({ path: args.path, namespace: "decky-shim" }));
    builder.onLoad({ filter: /.*/, namespace: "decky-shim" }, () => ({ contents:
      "export const findModuleChild=()=>()=>{}; export const useQuickAccessVisible=()=>false; export const callable=()=>()=>Promise.resolve({});" }));
  } }],
});
await writeFile(path.join(root, ".cache/overlay-preview.html"), `<!doctype html><html><head><meta charset="utf-8"><title>Decky Pinyin overlay test</title></head><body style="margin:0;background:#141b26"><img src="../artifacts/ocr-fixture.png" style="position:fixed;width:100vw;height:100vh;object-fit:fill"/><div id="root"></div><script src="./overlay-preview.js"></script></body></html>`);
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.goto(pathToFileURL(path.join(root, ".cache/overlay-preview.html")).href);
  await page.locator("ruby").first().waitFor();
  assert.equal(await page.locator("rt").first().textContent(), "nǐ");
  const checkBounds = async () => {
    const bounds = await page.locator('[aria-live="polite"]').evaluate((el) => {
      const outer = el.getBoundingClientRect();
      const children = [...el.children].map((child) => {
        const rect = child.getBoundingClientRect();
        return { bottom: rect.bottom, right: rect.right, height: child.clientHeight, scrollHeight: child.scrollHeight };
      });
      return { outer: { bottom: outer.bottom, right: outer.right }, children };
    });
    for (const child of bounds.children) {
      assert(child.bottom <= bounds.outer.bottom + 1, "Overlay clips content vertically");
      assert(child.right <= bounds.outer.right + 1, "Overlay clips content horizontally");
      assert(child.scrollHeight <= child.height + 1, "Overlay hides text");
    }
  };
  await checkBounds();
  await page.evaluate(() => window.preview.stale());
  await page.waitForTimeout(100);
  assert(await page.locator("ruby").count() > 0, "Old RPC state replaced newer live result");
  await page.screenshot({ path: path.join(root, "artifacts/overlay-preview.png") });
  await page.evaluate(() => window.preview.large());
  await page.waitForTimeout(100);
  await checkBounds();
  await page.evaluate(() => window.preview.upper());
  await page.waitForTimeout(100);
  const box = await page.locator('[aria-live="polite"]').boundingBox();
  assert(box.y >= 580, "Upper capture must dock overlay at bottom");
  await page.evaluate(() => window.preview.stop());
  await page.waitForTimeout(100);
  assert.equal(await page.locator("ruby").count(), 0);
  assert.deepEqual(errors, []);
  console.log("Overlay verified at 1280×800: ruby alignment, text fit, dock switching, stale-state rejection, stop cleanup. Steam composition hook is stubbed; physical Deck still required.");
} finally {
  await browser.close();
}
