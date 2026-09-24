import { fetchNoCors } from "@decky/api";
import manifest from "../package.json";

export const currentVersion = manifest.version;
export const releasesURL = "https://github.com/xmfan/decky-pinyin/releases";
const repository = "https://api.github.com/repos/xmfan/decky-pinyin";

interface Asset { name: string; browser_download_url: string; size: number; }
interface Release { tag_name: string; draft: boolean; prerelease: boolean; assets: Asset[]; }
export interface UpdateInfo {
  version: string;
  available: boolean;
  prerelease: boolean;
  size: number;
  url: string;
  sha256: string;
}

const versionParts = (value: string) => /^v?\d+\.\d+\.\d+$/.test(value) ? value.replace(/^v/, "").split(".").map(Number) : null;
const compareVersions = (a: number[], b: number[]) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];

async function downloadText(url: string): Promise<string> {
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), 20000);
  try {
    const response = await fetchNoCors(url, { signal: abort.signal, cache: "no-store" });
    if (!response.ok) {
      if (response.status === 403 || response.status === 429) throw new Error("GitHub limited update requests. Try again later.");
      throw new Error(`GitHub returned HTTP ${response.status}. Try again later.`);
    }
    return await response.text();
  } catch (error) {
    if (abort.signal.aborted) throw new Error("Update check timed out. Check your internet connection and try again.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

// Include GitHub prereleases: our numbered offline builds are published that way.
// Only this repository's exact versioned offline ZIP and checksum are eligible.
export async function checkForUpdate(): Promise<UpdateInfo> {
  const data: unknown = JSON.parse(await downloadText(`${repository}/releases?per_page=100`));
  if (!Array.isArray(data)) throw new Error("GitHub returned an invalid release list.");
  const releases = (data as Release[]).filter(release => release && !release.draft && typeof release.tag_name === "string" && versionParts(release.tag_name));
  releases.sort((a, b) => compareVersions(versionParts(b.tag_name)!, versionParts(a.tag_name)!));
  const release = releases[0];
  if (!release) throw new Error("No published offline release was found.");
  const version = release.tag_name.replace(/^v/, "");
  const available = compareVersions(versionParts(version)!, versionParts(currentVersion)!) > 0;
  const info: UpdateInfo = { version, available, prerelease: !!release.prerelease, size: 0, url: "", sha256: "" };
  if (!available) return info;
  const filename = `Decky-Pinyin-${version}-offline.zip`;
  const base = `${releasesURL}/download/${release.tag_name}/`;
  const asset = (name: string) => release.assets?.find(item => item.name === name && item.browser_download_url === base + name);
  const zip = asset(filename), checksum = asset(`${filename}.sha256`);
  if (!zip || !checksum || !Number.isSafeInteger(zip.size) || zip.size <= 0) {
    throw new Error("The newest release is missing its offline ZIP or checksum. Try again later.");
  }
  const text = (await downloadText(checksum.browser_download_url)).trim();
  const match = /^([a-fA-F0-9]{64})\s+\*?([^\r\n]+)$/.exec(text);
  if (!match || match[2] !== filename) throw new Error("The release checksum is invalid. Update was not started.");
  return { ...info, size: zip.size, url: zip.browser_download_url, sha256: match[1].toLowerCase() };
}

export async function requestUpdate(info: UpdateInfo): Promise<void> {
  if (!info.available || !info.url || !/^[a-f0-9]{64}$/.test(info.sha256)) throw new Error("Check for updates before installing.");
  // @decky/api's callable is scoped to this plugin's Python methods. The loader
  // exposes its installer through the global router used by its own store UI.
  const backend = (globalThis as unknown as { DeckyBackend?: { call: (route: string, ...args: unknown[]) => Promise<unknown> } }).DeckyBackend;
  if (typeof backend?.call !== "function") throw new Error("Decky's installer is unavailable. Update Decky or install the ZIP manually from GitHub Releases.");
  // InstallType.UPDATE = 2. Decky prompts, verifies the hash, installs and reloads.
  // This promise acknowledges the prompt; it does not mean installation finished.
  await backend.call("utilities/install_plugin", info.url, "Decky Pinyin", info.version, info.sha256, 2);
}
