import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { useState } from "react";
import { checkForUpdate, currentVersion, requestUpdate } from "./updates";
import type { UpdateInfo } from "./updates";

export function UpdatesPanel() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const check = async () => {
    setBusy(true); setInfo(null); setError(""); setMessage("Checking GitHub…");
    try {
      const next = await checkForUpdate();
      setInfo(next);
      setMessage(next.available ? `Available: ${next.version}${next.prerelease ? " (prerelease)" : ""} · ${Math.ceil(next.size / 1024 ** 2)} MB` : "You’re up to date.");
    } catch (err) {
      setMessage(""); setError(`Could not check for updates. ${String(err)}`);
    } finally { setBusy(false); }
  };
  const install = async () => {
    if (!info) return;
    setBusy(true); setError("");
    try {
      await requestUpdate(info);
      setMessage("Confirm the update in Decky’s dialog. Decky will download it and reload the plugin. If you cancel, you can try again here.");
    } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  };
  return <PanelSection title="Updates">
    <PanelSectionRow><div style={{ fontSize: 12, lineHeight: 1.5 }}>
      Installed: {currentVersion}<br />Checks and downloads need internet. Translation and speech stay offline.
    </div></PanelSectionRow>
    <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void check()}>{busy ? "Please wait…" : "Check for updates"}</ButtonItem></PanelSectionRow>
    {info?.available && <PanelSectionRow><ButtonItem disabled={busy} layout="below" onClick={() => void install()}>Update to {info.version}</ButtonItem></PanelSectionRow>}
    {message && <PanelSectionRow><div role="status" style={{ fontSize: 12 }}>{message}</div></PanelSectionRow>}
    {error && <PanelSectionRow><div role="alert" style={{ fontSize: 12, color: "#ffb4ab" }}>{error}</div></PanelSectionRow>}
  </PanelSection>;
}
