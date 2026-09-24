import { findModuleChild, useQuickAccessVisible } from "@decky/ui";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { placeLabels } from "./layout";
import type { Placement } from "./layout";
import { rpc, Store, useStateSnapshot } from "./store";

// Steam's composition hook maintains the notification layer while gameplay keeps focus.
// Discovery follows Decky-Translator's ActivationIndicator (GPL-3.0, see THIRD_PARTY.md).
const useComposition: ((level: number) => void) | undefined = findModuleChild((module: unknown) => {
  if (!module || typeof module !== "object") return undefined;
  return Object.values(module).find((fn: unknown) => {
    if (typeof fn !== "function") return false;
    const source = fn.toString();
    return source.includes("AddMinimumCompositionStateRequest") &&
      source.includes("ChangeMinimumCompositionStateRequest") &&
      source.includes("RemoveMinimumCompositionStateRequest") &&
      !source.includes("m_mapCompositionStateRequests");
  });
});

export const overlaySupported = typeof useComposition === "function";

function Composition() {
  useComposition?.(1);
  return null;
}

export function Overlay({ store }: { store: Store }) {
  const state = useStateSnapshot(store);
  const menuOpen = useQuickAccessVisible();
  const result = state?.result;
  const screenshot = state?.screenshot;
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight });
  const [natural, setNatural] = useState({ width: 1280, height: 800 });
  const [positions, setPositions] = useState<Placement[]>([]);
  const labels = useRef<(HTMLDivElement | null)[]>([]);
  useEffect(() => {
    const resize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  const sourceWidth = result?.width || natural.width;
  const sourceHeight = result?.height || natural.height;
  const scale = Math.min(viewport.width / sourceWidth, viewport.height / sourceHeight);
  const width = sourceWidth * scale, height = sourceHeight * scale;
  useLayoutEffect(() => {
    if (!result) return;
    const sizes = result.lines.map((_, index) => ({ width: labels.current[index]?.offsetWidth || 100, height: labels.current[index]?.offsetHeight || 48 }));
    setPositions(placeLabels(result.lines.map((line) => line.rect), sizes, width, height));
  }, [result, width, height, state?.settings.font_size, state?.settings.translation, menuOpen]);
  if (!overlaySupported || menuOpen || state?.status !== "running" || (!screenshot && !result?.lines.length)) return null;
  const speak = (line: number) => { void rpc.speak(line).then(store.update).catch(console.error); };
  const speaking = state.speech_status === "generating" || state.speech_status === "speaking";
  return <>
    <Composition />
    <div style={{ position: "fixed", inset: 0, background: "#000", zIndex: 7999, pointerEvents: "none" }} />
    <div data-screenshot-plane style={{ position: "fixed", left: (viewport.width - width) / 2,
      top: (viewport.height - height) / 2, width, height, zIndex: 8000, pointerEvents: "none" }}>
      {screenshot && <img alt="Captured game screen" src={screenshot} onLoad={(event) => setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
        style={{ width: "100%", height: "100%", objectFit: "contain" }} />}
      <div aria-live="polite">
        {result?.lines.map((line, index) => {
          const maxWidth = Math.max(100, width - 8);
          const cardWidth = Math.min(maxWidth, Math.max(150, (line.rect.right - line.rect.left) * width + 28));
          const position = positions[index];
          return <div key={index} data-reading-label data-line={index} ref={(node) => { labels.current[index] = node; }}
            style={{ position: "absolute", left: position?.left ?? line.rect.left * width,
              top: position?.top ?? line.rect.top * height, width: cardWidth, maxHeight: height - 48,
              padding: "5px 8px", boxSizing: "border-box", borderRadius: 5, color: "#f5f7fa", background: "rgba(9,17,26,.94)",
              fontFamily: "sans-serif", overflowY: "auto", pointerEvents: "auto" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <div style={{ flex: 1, minWidth: 0, fontSize: state.settings.font_size, lineHeight: 1.85, overflowWrap: "anywhere" }}>
                {line.tokens.map((token, i) => token.pinyin ? <ruby key={i} style={{ marginRight: 2 }}>{token.text}<rt style={{ fontSize: ".64em", color: "#98dfc2" }}>{token.pinyin}</rt></ruby> : <span key={i}>{token.text}</span>)}
              </div>
              <button aria-label={`Speak Chinese line ${index + 1}`} onClick={() => speak(index)}
                style={{ color: "#98dfc2", background: "transparent", border: 0, padding: 5, fontSize: 18 }}>🔊</button>
            </div>
            {state.settings.translation && <div style={{ fontSize: Math.max(13, state.settings.font_size - 3), lineHeight: 1.3, color: "#e1e8f2" }}>
              {line.translation || (result.translating ? "Translating…" : result.translation_error ? "Translation unavailable" : "")}
            </div>}
          </div>;
        })}
      </div>
    </div>
    <div style={{ position: "fixed", right: 8, top: 6, zIndex: 8001, padding: "4px 8px", borderRadius: 4,
      background: "rgba(9,17,26,.88)", color: "#a4ccad", fontSize: 11, pointerEvents: "auto" }}>
      L5 · 0.2s to dismiss
      {state.busy && <span> · {state.message}</span>}
      {!state.busy && !result?.lines.length && <span> · {state.message}</span>}
      {speaking && <button onClick={() => void rpc.stopSpeech().then(store.update)} style={{ marginLeft: 8 }}>Stop speech</button>}
      {state.speech_error && <span> · Speech: {state.speech_error}</span>}
    </div>
  </>;
}
