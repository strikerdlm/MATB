"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAppLocale } from "@/lib/i18n";
import type { OpenMatbVisualProfile } from "@/types/openmatb";

function nextPatchVersion(version: string): string {
  const [major, minor, patch] = version.split(".").map(Number);
  return `${major}.${minor}.${patch + 1}`;
}

export function ProfileManager({
  open,
  source,
  busy,
  onOpenChange,
  onClone,
}: {
  open: boolean;
  source: OpenMatbVisualProfile;
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onClone: (value: { profile_id: string; version: string; label: string }) => void;
}) {
  const { copy } = useAppLocale();
  const [profileId, setProfileId] = useState("");
  const [version, setVersion] = useState("");
  const [label, setLabel] = useState("");
  useEffect(() => {
    if (!open) return;
    setProfileId(source.bundled ? `${source.profile_id}-custom` : source.profile_id);
    setVersion(source.bundled ? "1.0.0" : nextPatchVersion(source.version));
    setLabel(`${source.label} — ${copy("personalizado", "custom")}`);
  }, [copy, open, source]);

  const valid = /^[a-z0-9][a-z0-9-]{2,63}$/.test(profileId)
    && /^\d+\.\d+\.\d+$/.test(version)
    && label.trim().length >= 3;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="fac-dialog">
        <DialogHeader>
          <DialogTitle>{copy("Clonar perfil visual", "Clone visual profile")}</DialogTitle>
          <DialogDescription>
            {copy("Los perfiles publicados y distribuidos son inmutables. Clone uno para crear un borrador versionado.", "Published and bundled profiles are immutable. Clone one to create a versioned draft.")}
          </DialogDescription>
        </DialogHeader>
        <div className="fac-dialog-form">
          <label><span>{copy("ID del perfil", "Profile ID")}</span><input value={profileId} onChange={(event) => setProfileId(event.target.value.toLowerCase())} /></label>
          <label><span>{copy("Versión semántica", "Semantic version")}</span><input value={version} onChange={(event) => setVersion(event.target.value)} /></label>
          <label><span>{copy("Etiqueta visible", "Display label")}</span><input value={label} onChange={(event) => setLabel(event.target.value)} /></label>
        </div>
        <DialogFooter>
          <button className="fac-button fac-button-secondary" type="button" disabled={busy} onClick={() => onOpenChange(false)}>{copy("Cancelar", "Cancel")}</button>
          <button className="fac-button fac-button-primary" type="button" disabled={busy || !valid} onClick={() => onClone({ profile_id: profileId, version, label: label.trim() })}>{copy("Crear borrador", "Create draft")}</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
