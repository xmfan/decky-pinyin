import { FaVolumeUp } from "react-icons/fa";
import { findModuleChild, useQuickAccessVisible } from "@decky/ui";
import { useLayoutEffect, useRef, useState } from "react";
import { paginateLabels } from "./layout";
import { OverlayPortal } from "./OverlayPortal";
import type { LabelPage } from "./layout";
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
  if (!overlaySupported || menuOpen || state?.status !== "running" || (!state.screenshot && !state.result?.lines.length)) return null;
  return <><Composition /><OverlayPortal><ReadingSurface store={store} /></OverlayPortal></>;
}

function ReadingSurface({ store }: { store: Store }) {
  const state = useStateSnapshot(store)!;
  const result = state.result;
  const surface = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ width: 1280, height: 800 });
  const [pages, setPages] = useState<LabelPage[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const labels = useRef<(HTMLDivElement | null)[]>([]);
  useLayoutEffect(() => {
    const element = surface.current!;
    const view = element.ownerDocument.defaultView!;
    const resize = () => {
      const width = element.clientWidth, height = element.clientHeight;
      if (width > 0 && height > 0) setViewport(previous => previous.width === width && previous.height === height ? previous : { width, height });
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    view.addEventListener("resize", resize);
    return () => { observer.disconnect(); view.removeEventListener("resize", resize); };
  }, []);
  const sourceWidth = result?.width || 1280;
  const sourceHeight = result?.height || 800;
  const scale = Math.min(viewport.width / sourceWidth, viewport.height / sourceHeight);
  const width = sourceWidth * scale, height = sourceHeight * scale;
  const selectedPage = Math.min(pageIndex, Math.max(0, pages.length - 1));
  const page = pages[selectedPage];
  useLayoutEffect(() => { setPageIndex(0); }, [result?.request_id, result?.revision]);
  const cardWidth = (index: number) => {
    const line = result!.lines[index];
    const font = state!.settings.font_size;
    const textWidth = line.tokens.reduce((sum, token) => sum + Math.max(token.text.length * font,
      token.pinyin.length * font * .64 * .6) + 2, 0) + 36;
    return Math.min(width - 24, 680, Math.max(240, textWidth, (line.rect.right - line.rect.left) * width + 16));
  };
  useLayoutEffect(() => {
    if (!result) return;
    const measure = () => {
      const sizes = result.lines.map((_, index) => ({ width: labels.current[index]?.offsetWidth || 360, height: labels.current[index]?.offsetHeight || 48 }));
      const next = paginateLabels(result.lines.map((line) => line.rect), sizes, width, height);
      setPages(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    };
    measure();
    const observer = new ResizeObserver(measure);
    labels.current.forEach(node => { if (node) observer.observe(node); });
    return () => observer.disconnect();
  }, [result, width, height, state?.settings.font_size, state?.settings.translation]);
  const speak = (line: number) => { void rpc.speak(line).then(store.update).catch(console.error); };
  const speaking = state.speech_status === "generating" || state.speech_status === "speaking";
  return <div ref={surface} data-reading-surface style={{ position: "fixed", inset: 0, width: "100vw", height: "100vh", pointerEvents: "none" }}>
    <div data-game-dimmer style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.08)", zIndex: 7999, pointerEvents: "none" }} />
    <div data-screenshot-plane style={{ position: "fixed", left: (viewport.width - width) / 2,
      top: (viewport.height - height) / 2, width, height, zIndex: 8000, pointerEvents: "none" }}>
      <div>
        {result?.lines.map((line, index) => {
          const slot = page?.indices.indexOf(index) ?? -1;
          const shown = slot >= 0;
          const position = shown ? page!.positions[slot] : undefined;
          return <div key={`${result.request_id}:${result.revision}:${index}`} data-reading-label={shown || undefined} data-line={index} aria-hidden={!shown} ref={(node) => { labels.current[index] = node; }}
            style={{ position: "absolute", visibility: shown ? "visible" : "hidden", left: position?.left ?? 4,
              top: position?.top ?? 32, width: cardWidth(index), maxHeight: height - 48,
              flexShrink: 0, writingMode: "horizontal-tb",
              padding: "3px 6px", boxSizing: "border-box", borderRadius: 5, color: "#f5f7fa", background: "rgba(9,17,26,.80)",
              fontFamily: "sans-serif", overflowY: "auto", pointerEvents: shown ? "auto" : "none" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <div style={{ flex: 1, minWidth: 0, fontSize: state.settings.font_size, lineHeight: 1.1, overflowWrap: "normal" }}>
                {line.tokens.map((token, i) => token.pinyin ? <ruby key={i} style={{ display: "inline-flex", flexDirection: "column-reverse", alignItems: "center", verticalAlign: "bottom", marginRight: 2, whiteSpace: "nowrap", lineHeight: 1.2 }}>{token.text}<rt style={{ display: "block", fontSize: ".64em", color: "#98dfc2", lineHeight: 1.15 }}>{token.pinyin}</rt></ruby> : <span key={i}>{token.text}</span>)}
              </div>
              <button aria-label={`Speak Chinese line ${index + 1}`} onClick={() => speak(index)}
                style={{ color: "#98dfc2", background: "transparent", border: 0, padding: 2, flexShrink: 0, lineHeight: 1 }}><FaVolumeUp size={14} aria-hidden="true" /></button>
            </div>
            {state.settings.translation && <div style={{ fontSize: Math.max(8, state.settings.font_size - 3), lineHeight: 1.2, color: "#e1e8f2" }}>
              {line.translation || (result.translating ? "Translating…" : result.translation_error ? "Translation unavailable" : "")}
            </div>}
          </div>;
        })}
      </div>
    </div>
    <div style={{ position: "fixed", right: 8, top: 6, zIndex: 8001, padding: "4px 8px", borderRadius: 4,
      background: "rgba(9,17,26,.80)", color: "#a4ccad", fontSize: 11, pointerEvents: "auto" }}>
      Tap L4 to refresh · Hold L4 / L5 0.2s to dismiss · {result?.lines.length || 0} labels
      {pages.length > 1 && <span data-label-pages>
        <button aria-label="Previous labels" disabled={selectedPage === 0} onClick={() => setPageIndex(selectedPage - 1)} style={{ marginLeft: 8 }}>Previous</button>
        <span> Page {selectedPage + 1} / {pages.length}</span>
        <button aria-label="Next labels" disabled={selectedPage === pages.length - 1} onClick={() => setPageIndex(selectedPage + 1)} style={{ marginLeft: 8 }}>Next</button>
      </span>}
      {state.busy && <span> · {state.message}</span>}
      {!state.busy && !result?.lines.length && <span> · {state.message}</span>}
      {speaking && <button onClick={() => void rpc.stopSpeech().then(store.update)} style={{ marginLeft: 8 }}>Stop speech</button>}
      {state.speech_error && <span> · Speech: {state.speech_error}</span>}
    </div>
  </div>;
}
