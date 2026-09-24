// Direct screenshot orchestration adapted from Decky-Translator's GameTranslatorLogic (GPL-3.0).
import { toaster } from "@decky/api";
import { Navigation } from "@decky/ui";
import { ActionType, Input, InputMode } from "./Input";
import type { ProgressInfo } from "./Input";
import { rpc, Store } from "./store";

export class Controller {
  readonly input = new Input();
  progress: ProgressInfo = { active: false, progress: 0, forDismiss: false };
  private progressListeners = new Set<() => void>();
  private run = 0;
  private capturing = false;
  private enabled = false;
  private initialized = false;
  private spoken = "";
  private closed = false;
  private lastError = "";
  private polling = false;
  private timer: ReturnType<typeof setInterval>;
  private unsubscribe: () => void;

  constructor(readonly store: Store) {
    this.input.setEnabled(false);
    this.input.setInputMode(InputMode.L5_BUTTON);
    this.input.setTranslateHoldTime(200);
    this.input.setDismissHoldTime(200);
    this.input.onProgress((progress) => {
      this.progress = progress;
      this.progressListeners.forEach((fn) => fn());
    });
    this.input.onShortcutPressed((action) => {
      void (action === ActionType.DISMISS ? this.dismiss() : this.capture()).catch(this.report);
    });
    this.unsubscribe = store.subscribe(() => {
      const state = store.snapshot();
      const enabled = state?.status === "running";
      if (enabled !== this.enabled) {
        this.enabled = enabled;
        this.input.setEnabled(enabled);
      }
      this.input.setOverlayVisible(!!(state?.screenshot || state?.result?.lines.length || state?.busy));
      const error = state && (state.status === "error" || state.message.startsWith("Capture failed:")) ? state.message : "";
      if (error && error !== this.lastError) this.report(error);
      this.lastError = error;
      const result = state?.result;
      const key = result ? `${result.request_id}:${result.revision}` : "";
      if (state?.settings.tts_auto && result?.lines.length && key !== this.spoken) {
        this.spoken = key;
        void rpc.speak(-1).then(store.update).catch(this.report);
      }
    });
    // Upstream uses backend RPC polling. Keep UI state current even if a Decky
    // event is missed while the Quick Access panel is closed.
    this.timer = setInterval(() => void this.refresh(), 500);
    void this.refresh();
  }

  private report = (error: unknown) => {
    console.error("Decky Pinyin capture", error);
    toaster.toast({ title: "Decky Pinyin", body: String(error), duration: 5000, critical: true });
  };

  private async refresh() {
    if (this.polling || this.closed) return;
    this.polling = true;
    try {
      const state = await rpc.updates(this.store.snapshot()?.version ?? -1);
      if (state && !this.closed) this.store.update(state);
      if (!this.initialized && state) {
        this.initialized = true;
        if (state.settings.enabled && state.installed && state.status === "stopped" && !this.closed) {
          const started = await rpc.start();
          if (!this.closed) this.store.update(started);
        }
      }
    }
    catch (error) { console.warn("Decky Pinyin state", error); }
    finally { this.polling = false; }
  }

  capture = async () => {
    if (this.capturing || this.store.snapshot()?.status !== "running") return rpc.get();
    const run = ++this.run;
    this.capturing = true;
    try {
      // Original sequence: clear old image, close Steam's menu, capture through
      // a direct backend call, then display the screenshot and model results.
      this.store.update(await rpc.dismiss());
      Navigation.CloseSideMenus();
      await new Promise((resolve) => setTimeout(resolve, 300));
      if (this.closed || run !== this.run) return rpc.get();
      const state = await rpc.capture();
      if (!this.closed && run === this.run) this.store.update(state);
      return state;
    } finally {
      if (run === this.run) this.capturing = false;
    }
  };

  dismiss = async () => {
    this.run++;
    this.capturing = false;
    const state = await rpc.dismiss();
    if (!this.closed) this.store.update(state);
    return state;
  };

  subscribeProgress = (fn: () => void) => {
    this.progressListeners.add(fn);
    return () => { this.progressListeners.delete(fn); };
  };
  progressSnapshot = () => this.progress;

  close() {
    this.closed = true;
    this.run++;
    this.input.unregister();
    this.unsubscribe();
    clearInterval(this.timer);
    this.progressListeners.clear();
  }
}
