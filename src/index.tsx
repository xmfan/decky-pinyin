import { addEventListener, definePlugin, removeEventListener, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { useSyncExternalStore } from "react";
import { BsTranslate } from "react-icons/bs";
import { Controller } from "./Controller";
import { Panel } from "./Panel";
import { ActivationIndicator } from "./ActivationIndicator";
import { Overlay } from "./Overlay";
import { rpc, Store } from "./store";
import type { State } from "./types";


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
    titleView: <div className={staticClasses.Title}>Decky Pinyin · 0.7.2</div>,
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
