import { addEventListener, definePlugin, removeEventListener, routerHook } from "@decky/api";
import { ButtonItem, DropdownItem, Navigation, PanelSection, PanelSectionRow, SliderField, staticClasses, ToggleField } from "@decky/ui";
import { useState, useSyncExternalStore } from "react";
import { BsTranslate } from "react-icons/bs";
import { Controller } from "./Controller";
import { ActivationIndicator } from "./ActivationIndicator";
import { Overlay, overlaySupported } from "./Overlay";
import { rpc, Store, useStateSnapshot } from "./store";
import type { Settings, State } from "./types";

function Panel({ store, controller }: { store: Store; controller: Controller }) {
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
  return <>
    <PanelSection title="Pinyin on demand">
      <PanelSectionRow><div style={{ fontSize: 13, color: state.status === "error" ? "#ffb4ab" : "#b8c9d9", marginBottom: 10 }}>
        {state.message}
        {!overlaySupported && <p>This Steam version’s overlay hook is unavailable. Update Decky before starting.</p>}
        {!state.installed && <p>Install the full offline ZIP, including models and runtime.</p>}
        {error && <p>{error}</p>}
        {state.input_status && <p>{state.input_status}</p>}
      </div></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy || (!running && (!overlaySupported || !state.installed))} layout="below" onClick={() => void action(async () => {
        const next = await (running ? rpc.stop() : rpc.start());
        if (!running && next.status !== "error") Navigation.CloseSideMenus();
        return next;
      })}>{running ? "Disable L5 shortcut" : "Enable L5 shortcut"}</ButtonItem></PanelSectionRow>
      {state.status === "running" && <>
        <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void action(controller.capture)}>{state.busy ? "Capture latest screen" : "Capture now"}</ButtonItem></PanelSectionRow>
        <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void action(controller.dismiss)}>Dismiss overlay</ButtonItem></PanelSectionRow>
      </>}
      <PanelSectionRow><div style={{ fontSize: 12, lineHeight: 1.5, color: "#a7b7c6" }}>
        Hold L5 for 0.2 seconds to capture or dismiss. Results stay visible until dismissed or replaced. Models stay loaded while enabled. Enabled by default. Settings changes restart the local models automatically.
      </div></PanelSectionRow>
    </PanelSection>
    <PanelSection title="Display">
      <PanelSectionRow><DropdownItem label="Chinese script" selectedOption={state.settings.chinese_script} disabled={busy}
        rgOptions={[{ data: "auto", label: "Auto · match detected script" }, { data: "traditional", label: "Traditional · 繁體中文" }, { data: "simplified", label: "Simplified · 简体中文" }]}
        onChange={(option) => save("chinese_script", option.data)} /></PanelSectionRow>
      <PanelSectionRow><ToggleField label="English translation" checked={state.settings.translation} disabled={busy} onChange={(value) => save("translation", value)} /></PanelSectionRow>
      <PanelSectionRow><DropdownItem label="Pinyin tones" selectedOption={state.settings.tone_style} disabled={busy}
        rgOptions={[{ data: "marks", label: "Tone marks · nǐ hǎo" }, { data: "numbers", label: "Numbers · ni3 hao3" }, { data: "none", label: "No tones · ni hao" }]}
        onChange={(option) => save("tone_style", option.data)} /></PanelSectionRow>
      <PanelSectionRow><SliderField label="Text size" value={state.settings.font_size} min={16} max={32} step={2} disabled={busy}
        onChange={(value) => save("font_size", value)} /></PanelSectionRow>
    </PanelSection>
    <PanelSection title="Speech">
      <PanelSectionRow><ToggleField label="Read Chinese after capture" checked={state.settings.tts_auto} disabled={busy} onChange={(value) => save("tts_auto", value)} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem disabled={busy || !state.result?.lines.length} layout="below" onClick={() => void action(() => rpc.speak(-1))}>Speak captured Chinese</ButtonItem></PanelSectionRow>
      {(state.speech_status === "generating" || state.speech_status === "speaking") && <PanelSectionRow><ButtonItem layout="below" onClick={() => void action(rpc.stopSpeech)}>Stop speech</ButtonItem></PanelSectionRow>}
      <PanelSectionRow><div style={{ fontSize: 12 }}>Offline Mandarin voice. Tap 🔊 beside a line to read it.{state.speech_error && <p>{state.speech_error}</p>}</div></PanelSectionRow>
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
  </>;
}

export default definePlugin(() => {
  const store = new Store();
  const listener = addEventListener<[State]>("pinyin_state", store.update);
  const controller = new Controller(store);
  routerHook.addGlobalComponent("DeckyPinyinOverlay", () => <Overlay store={store} />);
  routerHook.addGlobalComponent("DeckyPinyinActivation", () => {
    const progress = useSyncExternalStore(controller.subscribeProgress, controller.progressSnapshot);
    return <ActivationIndicator visible={progress.active} progress={progress.progress}
      forDismiss={progress.forDismiss} text={progress.forDismiss ? "Dismiss" : "Capture"} />;
  });
  const steam = (window as unknown as { SteamClient?: { User?: { RegisterForPrepareForSystemSuspendProgress?: (fn: () => void) => { unregister: () => void } } } }).SteamClient;
  const suspend = steam?.User?.RegisterForPrepareForSystemSuspendProgress?.(() => { void rpc.pause().then(store.update).catch(console.error); });
  return {
    name: "Decky Pinyin",
    titleView: <div className={staticClasses.Title}>Decky Pinyin</div>,
    content: <Panel store={store} controller={controller} />,
    icon: <BsTranslate />,
    alwaysRender: true,
    onDismount() {
      controller.close();
      removeEventListener("pinyin_state", listener);
      suspend?.unregister();
      routerHook.removeGlobalComponent("DeckyPinyinOverlay");
      routerHook.removeGlobalComponent("DeckyPinyinActivation");
      void rpc.pause().catch(console.error);
    },
  };
});
