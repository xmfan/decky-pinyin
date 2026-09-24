import { callable } from "@decky/api";
import { useSyncExternalStore } from "react";
import type { Settings, State } from "./types";

export const rpc = {
  get: callable<[], State>("get_state"),
  start: callable<[], State>("start"),
  stop: callable<[], State>("stop"),
  capture: callable<[], State>("capture"),
  dismiss: callable<[], State>("dismiss"),
  save: callable<[settings: Settings], State>("save_settings"),
};

export class Store {
  state: State | null = null;
  received = 0;
  private listeners = new Set<() => void>();
  update = (state: State) => {
    // A slow RPC reply must not roll back a newer streamed event.
    if (this.state && state.version < this.state.version) return;
    this.state = state;
    this.received = Date.now();
    this.listeners.forEach((fn) => fn());
  };
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => { this.listeners.delete(fn); };
  };
  snapshot = () => this.state;
}

export const useStateSnapshot = (store: Store) => useSyncExternalStore(store.subscribe, store.snapshot);
