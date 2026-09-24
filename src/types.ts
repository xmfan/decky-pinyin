export interface Settings {
  interval_ms: number;
  region: "subtitles" | "lower" | "upper";
  translation: boolean;
  tone_style: "marks" | "numbers" | "none";
  font_size: number;
  confidence: number;
  threads: number;
  ocr_device: "cpu" | "gpu" | "auto";
}

export interface Result {
  revision: number;
  lines: { text: string; confidence: number; tokens: { text: string; pinyin: string }[] }[];
  translation: string;
  translating: boolean;
  translation_error?: string;
  ocr_ms: number;
  pinyin_ms: number;
  translation_ms: number;
  age_ms: number;
  skipped: number;
  ocr_device: "cpu" | "gpu";
  ocr_notice: string;
}

export interface State {
  version: number;
  status: "stopped" | "loading" | "running" | "error";
  message: string;
  result: Result | null;
  settings: Settings;
  installed: boolean;
}
