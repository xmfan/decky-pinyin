import { ButtonItem, DropdownItem, Navigation, PanelSection, PanelSectionRow, SliderField, ToggleField } from "@decky/ui";
import { UpdatesPanel } from "./UpdatesPanel";
import { useState } from "react";
import { Controller } from "./Controller";
import { overlaySupported } from "./Overlay";
import { rpc, Store, useStateSnapshot } from "./store";
import type { Settings, State } from "./types";

export function Panel({ store, controller }: { store: Store; controller: Controller }) {
  const state = useStateSnapshot(store);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const action = async (fn: () => Promise<State>) => {
    setBusy(true);
    setError("");
    try { store.update(await fn()); }
    catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  };
  if (!state) return <PanelSection><PanelSectionRow>
    <div>Connecting to Decky Pinyin…</div>
    <ButtonItem onClick={() => void action(rpc.get)}>Retry connection</ButtonItem>
    {error && <div>{error}</div>}
  </PanelSectionRow></PanelSection>;
  const running = state.status === "running" || state.status === "loading";
  const save = <K extends keyof Settings>(key: K, value: Settings[K]) => void action(() => rpc.save({ ...state.settings, [key]: value }));
  return <div data-pinyin-panel>
    <PanelSection title="Pinyin on demand">
      <PanelSectionRow><ButtonItem disabled={busy || (!running && (!overlaySupported || !state.installed))} layout="below" onClick={() => void action(async () => {
        const next = await (running ? rpc.stop() : rpc.start());
        if (!running && next.status !== "error") Navigation.CloseSideMenus();
        return next;
      })}>{running ? "Disable L4 / L5 shortcuts" : "Enable L4 / L5 shortcuts"}</ButtonItem></PanelSectionRow>
      <PanelSectionRow><div style={{ fontSize: 14, marginBottom: 8 }}>L4 · Simplified 简体<br />L5 · Traditional 繁體</div></PanelSectionRow>
      <PanelSectionRow><ToggleField label="Read Chinese after capture" checked={state.settings.tts_auto} disabled={busy} onChange={(value) => save("tts_auto", value)} /></PanelSectionRow>
      {state.status === "running" && <>
        <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void action(() => controller.capture("simplified"))}>Capture Simplified · L4</ButtonItem></PanelSectionRow>
        <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void action(() => controller.capture("traditional"))}>Capture Traditional · L5</ButtonItem></PanelSectionRow>
        <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void action(controller.dismiss)}>Dismiss overlay</ButtonItem></PanelSectionRow>
      </>}
      <PanelSectionRow><div style={{ fontSize: 12, lineHeight: 1.5, color: "#a7b7c6" }}>
        Hold either key for 0.2 seconds to capture. With labels visible, tap L4 to refresh the current script or hold either key to dismiss.
      </div></PanelSectionRow>
      <PanelSectionRow><div style={{ fontSize: 13, color: state.status === "error" ? "#ffb4ab" : "#b8c9d9", marginBottom: 10 }}>
        {state.message}
        {!overlaySupported && <p>This Steam version’s overlay hook is unavailable. Update Decky before starting.</p>}
        {!state.installed && <p>Install the full offline ZIP, including models and runtime.</p>}
        {error && <p>{error}</p>}
        {state.input_status && <p>{state.input_status}</p>}
      </div></PanelSectionRow>
    </PanelSection>
    <UpdatesPanel />
    <PanelSection title="Display">

      <PanelSectionRow><ToggleField label="English translation" checked={state.settings.translation} disabled={busy} onChange={(value) => save("translation", value)} /></PanelSectionRow>
      <PanelSectionRow><DropdownItem label="Pinyin tones" selectedOption={state.settings.tone_style} disabled={busy}
        rgOptions={[{ data: "marks", label: "Tone marks · nǐ hǎo" }, { data: "numbers", label: "Numbers · ni3 hao3" }, { data: "none", label: "No tones · ni hao" }]}
        onChange={(option) => save("tone_style", option.data)} /></PanelSectionRow>
      <PanelSectionRow><SliderField label="Text size" value={state.settings.font_size} min={14} max={32} step={2} disabled={busy}
        onChange={(value) => save("font_size", value)} /></PanelSectionRow>
    </PanelSection>
    <PanelSection title="Speech">

      <PanelSectionRow><ButtonItem disabled={busy || !state.result?.lines.length} layout="below" onClick={() => void action(() => rpc.speak(-1))}>Speak captured Chinese</ButtonItem></PanelSectionRow>
      {(state.speech_status === "generating" || state.speech_status === "speaking") && <PanelSectionRow><ButtonItem layout="below" onClick={() => void action(rpc.stopSpeech)}>Stop speech</ButtonItem></PanelSectionRow>}
      <PanelSectionRow><div style={{ fontSize: 12 }}>Offline Mandarin · Piper Huayan medium. Tap the speaker icon beside a line to read it.{state.speech_error && <p>{state.speech_error}</p>}</div></PanelSectionRow>
    </PanelSection>
    <PanelSection title="Performance">
      <PanelSectionRow><DropdownItem label="OCR processor" selectedOption={state.settings.ocr_device} disabled={busy}
        rgOptions={[{ data: "auto", label: "Try GPU · fall back to CPU" }, { data: "gpu", label: "GPU · experimental" }, { data: "cpu", label: "CPU" }]}
        onChange={(option) => save("ocr_device", option.data)} /></PanelSectionRow>
      <PanelSectionRow><DropdownItem label="CPU threads per model" selectedOption={state.settings.threads} disabled={busy}
        rgOptions={[{ data: 1, label: "1 · light" }, { data: 2, label: "2 · balanced" }, { data: 3, label: "3" }, { data: 4, label: "4 · more CPU" }]}
        onChange={(option) => save("threads", option.data)} /></PanelSectionRow>
      {state.result && <PanelSectionRow><div style={{ fontSize: 12, lineHeight: 1.5 }}>
        OCR ({state.result.ocr_device}) {state.result.ocr_ms} ms · Pinyin {state.result.pinyin_ms} ms<br />
        Translation {state.result.translation_ms} ms
        {state.result.ocr_notice && <p>{state.result.ocr_notice}</p>}
        {state.result.translation_error && <p>{state.result.translation_error}</p>}
      </div></PanelSectionRow>}
    </PanelSection>
  </div>;
}

