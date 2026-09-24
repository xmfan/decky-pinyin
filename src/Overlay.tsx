import { findModuleChild, useQuickAccessVisible } from "@decky/ui";
import { Store, useStateSnapshot } from "./store";

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
  if (!overlaySupported || menuOpen || state?.status !== "running" || !result?.lines.length) return null;
  const bottom = state.settings.region === "upper";
  return <>
    <Composition />
    <div aria-live="polite" style={{ position: "fixed", left: 0, right: 0, [bottom ? "bottom" : "top"]: 0,
      maxHeight: "27vh", boxSizing: "border-box", zIndex: 8000, pointerEvents: "none", padding: "10px 24px",
      color: "#f5f7fa", background: "rgba(9, 17, 26, 0.92)", fontFamily: "sans-serif", overflow: "hidden" }}>
      <div style={{ color: "#a4ccad", fontSize: 11, letterSpacing: "0.12em", marginBottom: 6 }}>DECKY PINYIN · LOCAL</div>
      <div style={{ fontSize: state.settings.font_size, lineHeight: 1.85, maxHeight: "14vh", overflow: "hidden" }}>
        {result.lines.map((line, lineIndex) => <span key={lineIndex} style={{ marginRight: 16 }}>
          {line.tokens.map((token, i) => token.pinyin ?
            <ruby key={i} style={{ marginRight: 3 }}>{token.text}<rt style={{ fontSize: "0.64em", color: "#98dfc2" }}>{token.pinyin}</rt></ruby> :
            <span key={i}>{token.text}</span>)}
        </span>)}
      </div>
      {state.settings.translation && <div style={{ fontSize: Math.max(16, state.settings.font_size - 2), lineHeight: 1.3, color: "#e1e8f2", marginTop: 6 }}>
        {result.translation_error ? "Translation unavailable — see plugin panel" : result.translation || (result.translating ? "Translating locally…" : "")}
      </div>}
    </div>
  </>;
}
