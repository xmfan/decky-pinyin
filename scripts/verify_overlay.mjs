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
await build({entryPoints:[path.join(root,"src/layout.ts")],bundle:true,platform:"node",format:"esm",outfile:path.join(root,".cache/layout-test.mjs")});
const {paginateLabels, labelsOverlap} = await import(pathToFileURL(path.join(root,".cache/layout-test.mjs")));
const rects = [.72,.78,.84,.90].map(top=>({left:.32,right:.84,top,bottom:top+.04}));
for (const heights of [[80,80,80,80],[45,120,65,90],[400,400,400,400]]) {
  const pages = paginateLabels(rects, heights.map(height=>({width:680,height})),1280,800);
  assert.deepEqual(pages.flatMap(p=>p.indices),[0,1,2,3]);
  assert.equal(pages.length,heights[0]===400 ? 4 : 1);
  for (const {positions} of pages) {
    assert(!labelsOverlap(positions));
    positions.forEach((box,i)=>{
      assert(box.top>=32 && box.top+box.height<=796);
      if(i) assert(box.top>=positions[i-1].top+positions[i-1].height+4);
    });
  }
}
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
  const rubyBoxes = await page.locator("[data-reading-label] rt").evaluateAll(els => els.map(el => { const b=el.getBoundingClientRect(); return {left:b.left,right:b.right,top:b.top,bottom:b.bottom}; }));
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
  // Model the clipping and global styles a host application can impose.
  await page.evaluate(() => {
    const root=document.getElementById("root");
    root.style.cssText="position:relative;transform:translate(100px,100px);width:200px;height:1px;overflow:hidden;clip-path:inset(0)";
    const css=document.createElement("style");css.id="host-css";
    css.textContent="ruby, rt, [aria-live], [data-reading-label] { visibility:hidden !important; width:1px !important; max-height:1px !important; overflow:hidden !important; }";
    document.head.append(css);
  });
  await page.waitForTimeout(100);
  await checkBounds();
  const painted = await page.locator("[data-reading-label]").first().evaluate(el => {
    const r=el.getBoundingClientRect();const root=el.getRootNode();
    const hit=root.elementFromPoint(r.left+12,r.top+12);
    return getComputedStyle(el).visibility==="visible" && hit && el.contains(hit);
  });
  assert(painted, "Host clipping or CSS hid the rendered labels");
  await page.screenshot({path:path.join(root,"artifacts/overlay-host-isolation.png")});
  await page.evaluate(()=>{document.getElementById("host-css").remove();document.getElementById("root").style.cssText="";});
  await page.evaluate(() => window.preview.narrow());
  await page.waitForTimeout(100);
  const narrow = await page.locator("[data-reading-label]").boundingBox();
  assert(narrow.width >= 240 && narrow.height < 140, "Narrow OCR boxes must not make vertical labels");
  await page.evaluate(() => window.preview.bottomDialogue());
  await page.waitForTimeout(100);
  const dialogue = await checkBounds();
  assert.equal(dialogue.length, 4, "Compact dialogue should fit on a single page");
  for (let i=1;i<dialogue.length;i++) assert(dialogue[i].top >= dialogue[i-1].bottom + 3, "Later dialogue must stay below earlier rows");
  assert(dialogue[0].top < .82 * 800, "Bottom overflow must move the group upward");
  assert.equal(await page.locator("[data-label-pages]").count(), 0);
  const fonts = await page.locator("[data-reading-label]").first().evaluate(el => ({
    chinese: getComputedStyle(el.querySelector("ruby")).fontSize,
    pinyin: getComputedStyle(el.querySelector("rt")).fontSize,
    english: getComputedStyle(el.lastElementChild).fontSize,
    emoji: el.textContent.includes("🔊"),
  }));
  assert.equal(fonts.chinese, "14px");assert.equal(fonts.english, "11px");
  assert(parseFloat(fonts.pinyin) < 10);assert.equal(fonts.emoji, false);
  await page.screenshot({path:path.join(root,"artifacts/overlay-bottom-dialogue.png")});
  await page.evaluate(() => window.preview.crowded());
  await page.waitForTimeout(100);
  assert.equal(await page.locator("[data-reading-list]").count(), 0, "The scrolling fallback must be removed");
  assert.equal(await page.locator("[data-label-pages]").count(), 1, "Dense text must expose page navigation");
  const seen = new Set();
  do {
    const visible = await checkBounds();
    assert(visible.length > 0, "A label page must never be blank");
    for(let i=0;i<visible.length;i++) for(let j=i+1;j<visible.length;j++) {
      const a=visible[i],b=visible[j];
      assert(a.right<=b.left || b.right<=a.left || a.bottom<=b.top || b.bottom<=a.top, "Labels overlap on a crowded page");
    }
    for(const index of await page.locator("[data-reading-label]").evaluateAll(els => els.map(el=>el.dataset.line))) seen.add(index);
    if(await page.getByRole("button", {name:"Next labels"}).isDisabled()) break;
    await page.getByRole("button", {name:"Next labels"}).click();
    await page.waitForTimeout(50);
  } while(seen.size < 9);
  assert.equal(seen.size, 8, "Every recognized line must be visible on a reachable page");
  await page.getByRole("button", {name:"Previous labels"}).click();
  assert(await page.getByRole("button", {name:"Next labels"}).isEnabled());
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
  assert.equal(await page.locator("[data-pinyin-overlay-host]").count(), 0, "Dismissed/stopped overlays must remove their portal");
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
  assert.deepEqual(await page.evaluate(()=>window.preview.updateRequests()), [], "Opening the panel must not contact GitHub automatically");
  const checkUpdate = () => page.getByRole("button", {name:"Check for updates",exact:true}).click();
  await checkUpdate();
  await page.getByRole("button",{name:"Update to 0.7.10",exact:true}).waitFor();
  assert.match(await page.getByRole("status").textContent(), /0.7.10.*prerelease/);
  await page.getByRole("button",{name:"Update to 0.7.10",exact:true}).click();
  assert.deepEqual(await page.evaluate(()=>window.preview.installRequests()), [[
    "utilities/install_plugin", "https://github.com/xmfan/decky-pinyin/releases/download/v0.7.10/Decky-Pinyin-0.7.10-offline.zip",
    "Decky Pinyin", "0.7.10", "a".repeat(64), 2,
  ]], "The native installer must receive the exact offline ZIP, version and checksum");
  assert.match(await page.getByRole("status").textContent(), /Confirm.*Decky/);
  // The installer call only opens Decky's prompt; cancellation allows retry.
  assert(await page.getByRole("button",{name:"Update to 0.7.10",exact:true}).isEnabled());
  for (const mode of ["missing-installer", "install-error"]) {
    await page.evaluate(mode=>window.preview.updateMode(mode),mode);
    await page.getByRole("button",{name:"Update to 0.7.10",exact:true}).click();
    await page.getByRole("alert").waitFor();
  }
  for (const mode of ["current", "older"]) {
    await page.evaluate(mode=>window.preview.updateMode(mode),mode);
    await checkUpdate();
    await page.getByRole("status").filter({hasText:"You’re up to date."}).waitFor();
    assert.equal(await page.getByRole("button",{name:/^Update to/}).count(),0,"No reinstall or downgrade may be offered");
  }
  for (const mode of ["missing-asset", "foreign-url", "bad-checksum", "offline", "rate-limit", "timeout"]) {
    await page.evaluate(mode=>window.preview.updateMode(mode),mode);
    await checkUpdate();
    if(mode === "timeout") await page.clock.runFor(21000);
    await page.getByRole("alert").waitFor();
    assert.equal(await page.getByRole("button",{name:/^Update to/}).count(),0,"Failed checks must not leave an installable update");
    assert(await page.getByRole("button",{name:"Check for updates",exact:true}).isEnabled(),"Failed checks must allow retry");
  }
  assert.equal((await page.evaluate(()=>window.preview.installRequests())).length,1,"Failed checks and unsupported installers must not install anything");
  // Steam may render components in a different window than the module loader.
  await page.setViewportSize({width:320,height:240});
  const popup = page.waitForEvent("popup");
  await page.goto(pathToFileURL(path.join(root, ".cache/overlay-preview.html")).href + "?other-window");
  const game = await popup;
  game.on("pageerror", error => errors.push(String(error)));
  await game.setViewportSize({width:1280,height:800});
  await game.locator("[data-reading-label]").first().waitFor();
  assert.equal(await game.locator("[data-reading-label]").count(), 2, "Labels must render in the game UI's document");
  assert.equal(await page.locator("[data-pinyin-overlay-host]").count(), 0, "No overlay may be attached to the loader document");
  const surface = await game.locator("[data-reading-surface]").boundingBox();
  assert.equal(surface.width,1280);assert.equal(surface.height,800);
  const first = await game.locator("[data-reading-label]").first().boundingBox();
  assert(Math.abs(first.x-162)<1 && Math.abs(first.y-641)<1, "Coordinates must use the 1280×800 game surface, not the 320×240 loader");
  await game.screenshot({path:path.join(root,"artifacts/overlay-other-window.png")});
  await page.setViewportSize({width:640,height:480});
  await game.waitForTimeout(100);
  const unaffected=await game.locator("[data-reading-label]").first().boundingBox();
  assert.deepEqual(unaffected,first,"Resizing the loader window must not move game labels");
  await game.setViewportSize({width:1920,height:1080});
  await game.waitForTimeout(100);
  const docked=await game.locator("[data-reading-label]").first().boundingBox();
  assert(Math.abs(docked.x-(96+162*1.35))<1 && Math.abs(docked.y-641*1.35)<1,"Game-window resize must update capture scaling and letterboxing");
  await page.evaluate(()=>window.preview.stop());
  await game.waitForTimeout(100);
  assert.equal(await game.locator("[data-pinyin-overlay-host]").count(),0,"Stopping must remove the host from its owner document");
  await game.close();
  assert.deepEqual(errors, []);
  console.log("Overlay verified at 1280×800: ruby alignment, text fit, L4/L5 script holds, default activation, source-anchored wide labels, non-overlapping pages, compact text and ordered bottom dialogue, host CSS/clipping isolation, separate loader/game windows and viewport scaling, translucent background, direct capture, dismiss cancellation, polling recovery, release selection/checksum validation and native update handoff. Steam composition hook is stubbed; physical Deck still required.");
} finally {
  await browser.close();
}
