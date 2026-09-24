import { createRoot } from "react-dom/client";
import { Overlay } from "../src/Overlay";
import { Store } from "../src/store";
import type { State } from "../src/types";

const text = "你好，欢迎来到这里。请打开地图，寻找附近的村庄。";
const pinyin = "nǐ hǎo _ huān yíng lái dào zhè lǐ _ qǐng dǎ kāi dì tú _ xún zhǎo fù jìn de cūn zhuāng _".split(" ");
const state: State = {
  version: 1,
  status: "running", message: "Local", installed: true,
  settings: { interval_ms: 500, region: "subtitles", translation: true, tone_style: "marks", font_size: 22, confidence: .65, threads: 2, ocr_device: "auto" },
  result: { revision: 1, lines: [{ text, confidence: .98, tokens: [...text].map((char, i) => ({ text: char, pinyin: pinyin[i] === "_" ? "" : pinyin[i] })) }],
    translation: "Hello, welcome here. Open the map and find a nearby village.", translating: false, ocr_ms: 122, pinyin_ms: 2, translation_ms: 54, age_ms: 180, skipped: 4, ocr_device: "cpu", ocr_notice: "" },
};
const store = new Store();
store.update(state);
(window as any).preview = {
  upper: () => store.update({ ...state, settings: { ...state.settings, region: "upper" } }),
  stop: () => store.update({ ...state, status: "stopped", result: null }),
  large: () => store.update({ ...state, settings: { ...state.settings, font_size: 32 } }),
  start: () => store.update(state),
  stale: () => store.update({ ...state, version: 0, status: "stopped", result: null }),
};
createRoot(document.getElementById("root")!).render(<Overlay store={store} />);
