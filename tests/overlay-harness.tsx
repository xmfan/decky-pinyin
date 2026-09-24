import { createRoot } from "react-dom/client";
import { Overlay } from "../src/Overlay";
import { Controller } from "../src/Controller";
import { Store } from "../src/store";
import type { State } from "../src/types";

const text = "你好，欢迎来到这里。请打开地图，寻找附近的村庄。";
const pinyin = "nǐ hǎo _ huān yíng lái dào zhè lǐ _ qǐng dǎ kāi dì tú _ xún zhǎo fù jìn de cūn zhuāng _".split(" ");
const state: State = {
  version: 1,
  status: "running", message: "Local", installed: true,
  settings: { translation: true, tone_style: "marks", font_size: 22, confidence: .65, threads: 2, ocr_device: "auto" },
  result: { revision: 1, lines: [{ text, confidence: .98, tokens: [...text].map((char, i) => ({ text: char, pinyin: pinyin[i] === "_" ? "" : pinyin[i] })) }],
    translation: "Hello, welcome here. Open the map and find a nearby village.", translating: false, ocr_ms: 122, pinyin_ms: 2, translation_ms: 54, age_ms: 180, ocr_device: "cpu", ocr_notice: "" },
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
const captures: { overlayVisible: boolean; menuClosed: boolean }[] = [];
(window as any).testRpc = async (name: string, ...args: unknown[]) => {
  if (name === "get_hidraw_button_state") return { success: true, buttons };
  if (name === "get_updates") return args[0] === backendState.version ? null : backendState;
  if (name === "dismiss") backendState = { ...backendState, version: backendState.version + 1, result: null, screenshot: null, busy: false };
  if (name === "capture") {
    captures.push({ overlayVisible: !!document.querySelector("ruby"), menuClosed: (window as any).menuClosed });
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
  press: () => { buttons = ["L4"]; },
  release: () => { buttons = []; },
  captures: () => captures,
  capture: () => { void controller!.capture(); },
  dismiss: () => { void controller!.dismiss(); },
  finish: () => { backendState = { ...backendState, version: backendState.version + 1, result: state.result, busy: false }; },
  closeController: () => controller!.close(),
});
createRoot(document.getElementById("root")!).render(<Overlay store={store} />);
