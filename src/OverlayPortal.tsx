import { useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";

// Keep Steam/Decky ancestor clipping, transforms and global CSS out of the
// reading surface. The host is removed on dismiss, suspend and plugin unload.
export function OverlayPortal({ children }: { children: ReactNode }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const [root, setRoot] = useState<ShadowRoot | null>(null);
  useLayoutEffect(() => {
    // Decky can render this component into another Steam window. Module-global
    // document/window still refer to the loader window in that case.
    const document = anchor.current!.ownerDocument;
    const host = document.createElement("div");
    host.dataset.pinyinOverlayHost = "";
    const styles = { all: "initial", position: "fixed", inset: "0", display: "block", width: "100vw", height: "100vh",
      overflow: "visible", transform: "none", opacity: "1", visibility: "visible", "z-index": "8000", "pointer-events": "none" };
    for (const [name, value] of Object.entries(styles)) host.style.setProperty(name, value, "important");
    const shadow = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `:host { font: 16px sans-serif; color: #f5f7fa; direction: ltr; writing-mode: horizontal-tb; }
      *, *::before, *::after { box-sizing: border-box; }
      button { font: inherit; cursor: pointer; }
      button:focus-visible { outline: 2px solid #98dfc2; outline-offset: 2px; }`;
    shadow.append(style);
    document.body.append(host);
    setRoot(shadow);
    return () => { host.remove(); };
  }, []);
  return <><span ref={anchor} data-pinyin-overlay-anchor style={{ display: "none" }} />{root ? createPortal(children, root) : null}</>;
}
