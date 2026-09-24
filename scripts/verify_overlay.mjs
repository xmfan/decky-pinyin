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
    builder.onResolve({ filter: /^@decky\/(ui|api)$/ }, () => ({ path: path.join(root, "tests/decky-shim.ts") }));
  } }],
});
await writeFile(path.join(root, ".cache/overlay-preview.html"), `<!doctype html><html><head><meta charset="utf-8"><title>Decky Pinyin overlay test</title></head><body style="margin:0;background:#141b26"><img src="../artifacts/ocr-fixture.png" style="position:fixed;width:100vw;height:100vh;object-fit:fill"/><div id="root"></div><script src="./overlay-preview.js"></script></body></html>`);
const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.clock.install();
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.goto(pathToFileURL(path.join(root, ".cache/overlay-preview.html")).href);
  await page.locator("ruby").first().waitFor();
  assert.equal(await page.locator("rt").first().textContent(), "nǐ");
  const checkBounds = async () => {
    const bounds = await page.locator('[data-reading-label]').evaluateAll((els) => els.map((el) => {
      const box = el.getBoundingClientRect();
      return { left: box.left, top: box.top, right: box.right, bottom: box.bottom, width: el.clientWidth, scrollWidth: el.scrollWidth };
    }));
    const viewport = page.viewportSize();
    for (const box of bounds) {
      assert(box.left >= 0 && box.top >= 0 && box.right <= viewport.width + 1 && box.bottom <= viewport.height + 1, "Label leaves screen");
      assert(box.scrollWidth <= box.width + 1, "Label clips text horizontally");
    }
    return bounds;
  };
  await checkBounds();
  await page.clock.fastForward(9000);
  assert(await page.locator("ruby").count() > 0, "Manual capture disappeared while reading");
  await page.evaluate(() => window.preview.stale());
  await page.waitForTimeout(100);
  assert(await page.locator("ruby").count() > 0, "Old RPC state replaced newer live result");
  const anchor = await page.locator('[data-reading-label]').first().boundingBox();
  assert(anchor.y > 400 && anchor.y < 610, "Pinyin must appear near the original subtitle, not at the top");
  await page.screenshot({ path: path.join(root, "artifacts/overlay-preview.png") });
  await page.evaluate(() => window.preview.large());
  await page.waitForTimeout(100);
  await checkBounds();
  await page.evaluate(() => window.preview.multi());
  await page.waitForTimeout(100);
  const boxes = await checkBounds();
  assert.equal(boxes.length, 3);
  assert(boxes[1].bottom <= boxes[2].top || boxes[2].bottom <= boxes[1].top, "Neighboring reading labels overlap");
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.waitForTimeout(100);
  await checkBounds();
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.evaluate(() => window.preview.stop());
  await page.waitForTimeout(100);
  assert.equal(await page.locator("ruby").count(), 0);
  await page.evaluate(() => window.preview.beginController());
  await page.clock.runFor(200);
  await page.evaluate(() => window.preview.l4());
  await page.clock.runFor(400);
  assert.equal((await page.evaluate(() => window.preview.captures())).length, 0, "L4 must no longer activate");
  await page.evaluate(() => window.preview.release());
  await page.clock.runFor(100);
  await page.evaluate(() => window.preview.press());
  await page.clock.runFor(150);
  assert.equal((await page.evaluate(() => window.preview.captures())).length, 0, "Short hold should not capture");
  await page.clock.runFor(100);
  await page.evaluate(() => window.preview.release());
  await page.clock.runFor(450);
  assert.deepEqual(await page.evaluate(() => window.preview.captures()), [{ overlayVisible: false, menuClosed: true }]);
  assert.equal(await page.locator('img[alt="Captured game screen"]').count(), 1, "Capture should show a screenshot before OCR");
  await page.evaluate(() => { window.preview.release(); window.preview.finish(); });
  await page.clock.runFor(600);
  assert(await page.locator("ruby").count() > 0, "Polling must recover model results without a frontend event");
  await page.getByRole("button", { name: "Speak Chinese line 1" }).click();
  assert.deepEqual(await page.evaluate(() => window.preview.speechRequests()), [0]);
  await page.evaluate(() => window.preview.autoSpeech());
  await page.clock.runFor(600);
  assert.deepEqual(await page.evaluate(() => window.preview.speechRequests()), [0, -1]);
  await page.evaluate(() => window.preview.finish());
  await page.clock.runFor(600);
  assert.deepEqual(await page.evaluate(() => window.preview.speechRequests()), [0, -1], "Result updates must not repeat automatic speech");

  await page.evaluate(() => window.preview.press());
  await page.clock.runFor(400);
  assert.equal(await page.locator('img[alt="Captured game screen"]').count(), 0, "Second hold dismisses screenshot");
  assert.equal(await page.locator("ruby").count(), 0);
  await page.evaluate(() => window.preview.release());
  await page.clock.runFor(300);
  await page.evaluate(() => window.preview.capture());
  await page.clock.runFor(100);
  await page.evaluate(() => window.preview.dismiss());
  await page.clock.runFor(400);
  assert.equal((await page.evaluate(() => window.preview.captures())).length, 1, "Dismiss must cancel pending direct capture");
  await page.evaluate(() => window.preview.capture());
  await page.clock.runFor(400);
  assert.equal((await page.evaluate(() => window.preview.captures())).length, 2, "Panel capture uses the direct path too");
  await page.evaluate(() => window.preview.closeController());
  await page.evaluate(() => { window.preview.startEnabled(); window.preview.makeController(); });
  await page.clock.runFor(200);
  assert.equal(await page.evaluate(() => window.preview.starts()), 1, "Enabled default must start models on load");
  await page.evaluate(() => { window.preview.closeController(); window.preview.startDisabled(); window.preview.makeController(); });
  await page.clock.runFor(200);
  assert.equal(await page.evaluate(() => window.preview.starts()), 1, "Explicitly disabled preference must remain disabled");
  await page.evaluate(() => window.preview.closeController());
  assert.deepEqual(errors, []);
  console.log("Overlay verified at 1280×800: ruby alignment, text fit, short L5 holds, default activation, positioned labels, direct capture, screenshot before OCR, dismiss cancellation, polling recovery. Steam composition hook is stubbed; physical Deck still required.");
} finally {
  await browser.close();
}
