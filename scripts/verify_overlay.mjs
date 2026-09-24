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
await writeFile(path.join(root, ".cache/overlay-preview.html"), `<!doctype html><html><head><meta charset="utf-8"><title>Decky Pinyin overlay test</title></head><body style="margin:0;background:#141b26"><img src="../artifacts/ocr-fixture.png" style="position:fixed;width:100vw;height:100vh;object-fit:fill;pointer-events:none;z-index:-1"/><div id="root"></div><script src="./overlay-preview.js"></script></body></html>`);
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
  const rubyBoxes = await page.locator("rt").evaluateAll(els => els.map(el => { const b=el.getBoundingClientRect(); return {left:b.left,right:b.right,top:b.top,bottom:b.bottom}; }));
  for(let i=0;i<rubyBoxes.length;i++) for(let j=i+1;j<rubyBoxes.length;j++) {
    const a=rubyBoxes[i], b=rubyBoxes[j];
    assert(a.right<=b.left || b.right<=a.left || a.bottom<=b.top || b.bottom<=a.top, "Pinyin syllables overlap");
  }
  await page.clock.fastForward(9000);
  assert(await page.locator("ruby").count() > 0, "Manual capture disappeared while reading");
  await page.evaluate(() => window.preview.stale());
  await page.waitForTimeout(100);
  assert(await page.locator("ruby").count() > 0, "Old RPC state replaced newer live result");
  const anchor = await page.locator('[data-reading-label]').first().boundingBox();
  assert(anchor.y >= 640 && anchor.y < 650, "First label must cover its original subtitle position");
  await page.screenshot({ path: path.join(root, "artifacts/overlay-preview.png") });
  assert.equal(await page.locator("#root img").count(), 0, "No full-screen captured image is rendered");
  assert.equal(await page.locator("[data-game-dimmer]").evaluate(el => getComputedStyle(el).backgroundColor), "rgba(0, 0, 0, 0.12)");
  await page.evaluate(() => window.preview.narrow());
  await page.waitForTimeout(100);
  const narrow = await page.locator("[data-reading-label]").boundingBox();
  assert(narrow.width >= 360 && narrow.height < 140, "Narrow OCR boxes must not make vertical labels");
  await page.evaluate(() => window.preview.crowded());
  await page.waitForTimeout(100);
  const list = page.locator("[data-reading-list]");
  assert.equal(await list.count(), 1, "Dense text must use the non-overlapping scroll fallback");
  const dense = await page.locator("[data-reading-label]").evaluateAll(els => els.map(el => {const b=el.getBoundingClientRect();return {top:b.top,bottom:b.bottom};}));
  assert.equal(dense.length, 8);
  for(let i=1;i<dense.length;i++) assert(dense[i].top >= dense[i-1].bottom, "Reading labels overlap");
  await page.locator('[data-reading-label]').last().scrollIntoViewIfNeeded();
  assert(await list.evaluate(el => el.scrollTop > 0), "All labels must remain reachable by scrolling");
  await page.evaluate(() => window.preview.large());
  await page.waitForTimeout(100);
  await checkBounds();
  await page.evaluate(() => window.preview.multi());
  await page.waitForTimeout(100);
  const boxes = await checkBounds();
  assert.equal(boxes.length, 3);
  for (let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++) {
    const a=boxes[i],b=boxes[j];
    assert(a.right<=b.left || b.right<=a.left || a.bottom<=b.top || b.bottom<=a.top, "Neighboring reading labels overlap");
  }
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.waitForTimeout(100);
  await checkBounds();
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.evaluate(() => window.preview.stop());
  await page.waitForTimeout(100);
  assert.equal(await page.locator("ruby").count(), 0);
  await page.evaluate(() => window.preview.beginController());
  await page.clock.runFor(200);
  await page.evaluate(() => window.preview.both());
  await page.clock.runFor(400);
  assert.equal((await page.evaluate(() => window.preview.captures())).length, 0, "Simultaneous keys must not choose an ambiguous script");
  await page.evaluate(() => window.preview.release());
  await page.clock.runFor(100);
  await page.evaluate(() => window.preview.press());
  await page.clock.runFor(150);
  assert.equal((await page.evaluate(() => window.preview.captures())).length, 0, "Short hold should not capture");
  await page.clock.runFor(100);
  await page.evaluate(() => window.preview.release());
  await page.clock.runFor(450);
  assert.deepEqual(await page.evaluate(() => window.preview.captures()), [{ overlayVisible: false, menuClosed: true, script: "traditional" }]);
  assert.equal(await page.locator('img[alt="Captured game screen"]').count(), 0, "Captured images must never cover the live game");
  assert.equal(await page.locator("[data-game-dimmer]").count(), 1);
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
  await page.evaluate(() => window.preview.l4());
  await page.clock.runFor(250);
  await page.evaluate(() => window.preview.release());
  await page.clock.runFor(450);
  assert.equal((await page.evaluate(() => window.preview.captures()))[1].script, "simplified", "L4 must select Simplified for this capture");
  await page.evaluate(() => window.preview.capture());
  await page.clock.runFor(100);
  await page.evaluate(() => window.preview.dismiss());
  await page.clock.runFor(400);
  assert.equal((await page.evaluate(() => window.preview.captures())).length, 2, "Dismiss must cancel pending direct capture");
  await page.evaluate(() => window.preview.capture());
  await page.clock.runFor(400);
  assert.equal((await page.evaluate(() => window.preview.captures())).length, 3, "Panel capture uses the direct path too");
  await page.evaluate(() => window.preview.closeController());
  await page.evaluate(() => { window.preview.startEnabled(); window.preview.makeController(); });
  await page.clock.runFor(200);
  assert.equal(await page.evaluate(() => window.preview.starts()), 1, "Enabled default must start models on load");
  await page.evaluate(() => { window.preview.closeController(); window.preview.startDisabled(); window.preview.makeController(); });
  await page.clock.runFor(200);
  assert.equal(await page.evaluate(() => window.preview.starts()), 1, "Explicitly disabled preference must remain disabled");
  await page.evaluate(() => window.preview.closeController());
  await page.goto(pathToFileURL(path.join(root, ".cache/overlay-preview.html")).href + "?panel");
  await page.getByRole("button", { name: "Capture Traditional · L5" }).click();
  assert.equal((await page.evaluate(() => window.preview.captures()))[0].script, "traditional");
  await page.getByRole("button", { name: "Capture Simplified · L4" }).click();
  assert.equal((await page.evaluate(() => window.preview.captures()))[1].script, "simplified");
  assert.equal(await page.getByLabel("Read Chinese after capture").count(), 1);
  assert.equal(await page.getByLabel("Text size").count(), 1);
  assert.deepEqual(errors, []);
  console.log("Overlay verified at 1280×800: ruby alignment, text fit, L4/L5 script holds, default activation, source-anchored wide labels, non-overlapping scroll fallback, translucent background, direct capture, dismiss cancellation, polling recovery. Steam composition hook is stubbed; physical Deck still required.");
} finally {
  await browser.close();
}
