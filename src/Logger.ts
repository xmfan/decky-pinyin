// Keep the upstream input adapter's logging interface without per-poll log noise.
export const logger = {
  debug: (..._args: unknown[]) => {},
  info: (..._args: unknown[]) => {},
  warn: (...args: unknown[]) => console.warn("Decky Pinyin", ...args),
  error: (...args: unknown[]) => console.error("Decky Pinyin", ...args),
};
