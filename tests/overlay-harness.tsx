import { createRoot } from "react-dom/client";
import { Panel } from "../src/Panel";
import { Overlay } from "../src/Overlay";
import { Controller } from "../src/Controller";
import { currentVersion } from "../src/updates";
import { Store } from "../src/store";
import type { State } from "../src/types";
import fixture from "../artifacts/overlay-fixture.json";

const state: State = {
  version: 1,
  status: "running", message: "Local", installed: true, screenshot: "../artifacts/ocr-fixture.png",
  settings: { enabled: true, chinese_script: "auto", tts_auto: false, translation: true, tone_style: "marks", font_size: 14, confidence: .65, threads: 2, ocr_device: "auto" },
  result: fixture,
};
const store = new Store();
store.update(state);
(window as any).preview = {
  stop: () => store.update({ ...state, status: "stopped", result: null }),
  large: () => store.update({ ...state, settings: { ...state.settings, font_size: 32 } }),
  start: () => store.update(state),
  stale: () => store.update({ ...state, version: 0, status: "stopped", result: null }),
};
let controller: Controller | null = null;
let backendState: State = state;
let buttons: string[] = [];
let starts = 0;
const speechRequests: number[] = [];
const captures: { overlayVisible: boolean; menuClosed: boolean; script: unknown }[] = [];
(window as any).testRpc = async (name: string, ...args: unknown[]) => {
  if (name === "get_hidraw_button_state") return { success: true, buttons };
  if (name === "start") { starts++; backendState = { ...backendState, version: backendState.version + 1, status: "running" }; }
  if (name === "speak") speechRequests.push(args[0] as number);
  if (name === "get_updates") return args[0] === backendState.version ? null : backendState;
  if (name === "dismiss") backendState = { ...backendState, version: backendState.version + 1, result: null, screenshot: null, busy: false };
  if (name === "capture") {
    captures.push({ overlayVisible: !!document.querySelector("[data-pinyin-overlay-host]")?.shadowRoot?.querySelector("[data-reading-label]"), menuClosed: (window as any).menuClosed, script: args[0] });
    backendState = { ...backendState, version: backendState.version + 1, result: null, screenshot: "../artifacts/ocr-fixture.png", busy: true, message: "Recognizing Chinese locally…" };
  }
  return backendState;
};
Object.assign((window as any).preview, {
  beginController: () => {
    backendState = { ...state, version: 10, result: null, screenshot: null };
    controller = new Controller(store);
    store.update(backendState);
  },
  both: () => { buttons = ["L4", "L5"]; },
  press: () => { buttons = ["L5"]; },
  release: () => { buttons = []; },
  captures: () => captures,
  l4: () => { buttons = ["L4"]; },
  startDisabled: () => { backendState = { ...backendState, version: backendState.version + 1, status: "stopped", result: null, settings: { ...backendState.settings, enabled: false } }; },
  startEnabled: () => { backendState = { ...backendState, version: backendState.version + 1, status: "stopped", result: null, settings: { ...backendState.settings, enabled: true } }; },
  tradition: () => store.update({ ...state, result: { ...state.result!, lines: [{ ...state.result!.lines[0], text: "銀行的行長喜歡旅行。", tokens: [..."銀行的行長喜歡旅行。"].map((text) => ({text, pinyin: "háng"})) }] } }),
  narrow: () => store.update({ ...state, result: { ...state.result!, lines: [{ ...state.result!.lines[0], rect: { left: .2, top: .4, right: .21, bottom: .45 } }] } }),
  crowded: () => store.update({ ...state, settings: { ...state.settings, font_size: 32 }, result: { ...state.result!, lines: Array.from({length: 8}, () => ({ ...state.result!.lines[0], tokens: Array(20).fill(state.result!.lines[0].tokens).flat(), rect: { left: .4, top: .5, right: .41, bottom: .55 } })) } }),
  bottomDialogue: () => store.update({ ...state, result: { ...state.result!, lines: [.82, .87, .92, .97].map(top => ({
    ...state.result!.lines[0], tokens: Array(3).fill(state.result!.lines[0].tokens).flat(),
    rect: { left: .32, top, right: .84, bottom: top + .04 },
  })) } }),
  multi: () => store.update({ ...state, result: { ...state.result!, lines: [
    { ...state.result!.lines[0], rect: { left: .02, top: .02, right: .43, bottom: .07 } },
    { ...state.result!.lines[0], rect: { left: .52, top: .72, right: .98, bottom: .79 } },
    { ...state.result!.lines[0], rect: { left: .52, top: .81, right: .98, bottom: .88 } },
  ] } }),
  capture: () => { void controller!.capture(); },
  dismiss: () => { void controller!.dismiss(); },
  finish: () => { backendState = { ...backendState, version: backendState.version + 1, result: state.result, busy: false }; },
  closeController: () => controller!.close(),
  makeController: () => { controller = new Controller(store); },
  starts: () => starts,
  speechRequests: () => speechRequests,
  autoSpeech: () => { backendState = { ...backendState, version: backendState.version + 1, settings: { ...backendState.settings, tts_auto: true } }; },
});
// Exercise public release checks without network access or a real install.
let updateMode = "available";
const updateRequests: string[] = [];
const installRequests: unknown[][] = [];
const checksum = "a".repeat(64);
const release = (version: string, draft = false) => {
  const name = `Decky-Pinyin-${version}-offline.zip`;
  const base = `https://github.com/xmfan/decky-pinyin/releases/download/v${version}/`;
  return {tag_name: `v${version}`, draft, prerelease: true, assets: [
    {name, size: 380000000, browser_download_url: base + name},
    {name: name + ".sha256", size: 97, browser_download_url: base + name + ".sha256"},
  ]};
};
const installer = {call: async (...args: unknown[]) => {
  if(updateMode === "install-error") throw new Error("Installer disconnected");
  installRequests.push(args);
}};
(window as any).DeckyBackend = installer;
(window as any).testFetch = async (url: string, init: RequestInit) => {
  updateRequests.push(url);
  if(updateMode === "offline") throw new Error("Network unavailable");
  if(updateMode === "timeout") return new Promise((_,reject)=>init.signal!.addEventListener("abort",()=>reject(new Error("aborted"))));
  if(updateMode === "rate-limit") return new Response("",{status:403});
  if(url.endsWith(".sha256")) return new Response(updateMode === "bad-checksum" ? "invalid" : `${checksum}  Decky-Pinyin-0.7.10-offline.zip\n`);
  const latest = release("0.7.10");
  if(updateMode === "missing-asset") latest.assets.pop();
  if(updateMode === "foreign-url") latest.assets[0].browser_download_url = "https://example.org/plugin.zip";
  return new Response(JSON.stringify(updateMode === "current" ? [release(currentVersion)] :
    updateMode === "older" ? [release("0.7.3")] : [release("0.7.9"), release("99.0.0",true), latest]));
};
Object.assign((window as any).preview, {
  updateMode: (mode: string) => { updateMode = mode; (window as any).DeckyBackend = mode === "missing-installer" ? undefined : installer; },
  updateRequests: () => updateRequests,
  installRequests: () => installRequests,
});
const panelController = { capture: async (script: string) => (window as any).testRpc("capture", script), dismiss: async () => (window as any).testRpc("dismiss") } as unknown as Controller;
const target = location.search.includes("other-window") ? window.open("about:blank", "pinyin-game-ui", "width=1280,height=800")! : window;
if (target !== window) {
  target.document.body.style.cssText = "margin:0;background:#141b26";
  target.document.body.innerHTML = '<div id="root"></div>';
  const image = target.document.createElement("img");
  image.src = new URL("../artifacts/ocr-fixture.png", location.href).href;
  image.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;object-fit:contain;pointer-events:none;z-index:-1";
  target.document.body.prepend(image);
}
createRoot(target.document.getElementById("root")!).render(location.search.includes("panel") ? <Panel store={store} controller={panelController} /> : <Overlay store={store} />);
