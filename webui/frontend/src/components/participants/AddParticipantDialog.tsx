"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createParticipant } from "@/lib/api";
import { useAppLocale } from "@/lib/i18n";
import { isParticipantId, normalizeParticipantId } from "@/lib/participant-id";

export function AddParticipantDialog({ onCreated }: { onCreated: () => void }) {
  const { copy } = useAppLocale();
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [callsign, setCallsign] = useState("");
  const [mission, setMission] = useState<"" | "ASTRA-1" | "ASTRA-2">("");
  const [date, setDate] = useState("");
  const [sex, setSex] = useState("");
  const [ageBand, setAgeBand] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const normalizedId = normalizeParticipantId(id);
  const idIsValid = isParticipantId(normalizedId);

  async function submit() {
    if (!idIsValid) {
      setErr(copy("Use un código seudonimizado con P y entre 2 y 6 dígitos, por ejemplo P01.", "Use a pseudonymous code with P and 2 to 6 digits, for example P01."));
      return;
    }
    setBusy(true); setErr(null);
    try {
      await createParticipant({ id: normalizedId, enrollment_date: date, sex: sex || undefined, age_band: ageBand || undefined, callsign: callsign.trim() || undefined, mission: mission || undefined });
      setOpen(false); setId(""); setCallsign(""); setMission(""); setDate(""); setSex(""); setAgeBand("");
      onCreated();
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button>{copy("Agregar participante", "Add participant")}</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>{copy("Agregar participante", "Add participant")}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label htmlFor="pcallsign">{copy("Indicativo (opcional)", "Callsign (optional)")}</Label><Input id="pcallsign" value={callsign} onChange={e => setCallsign(e.target.value)} maxLength={60} /></div>
          <div><Label htmlFor="pmission">{copy("Misión", "Mission")}</Label><select id="pmission" className="native-select mt-1 w-full" value={mission} onChange={e => setMission(e.target.value as typeof mission)}><option value="">{copy("Protocolo general", "General protocol")}</option><option>ASTRA-1</option><option>ASTRA-2</option></select></div>
          <div>
            <Label htmlFor="pid">{copy("Código seudonimizado", "Pseudonymous code")}</Label>
            <Input
              id="pid"
              value={id}
              onChange={(e) => { setId(e.target.value); setErr(null); }}
              onBlur={() => { if (id) setId(normalizedId); }}
              placeholder="P01"
              autoComplete="off"
              aria-describedby="pid-help"
              aria-invalid={Boolean(id) && !idIsValid}
            />
            <p id="pid-help" className={`mt-1 text-xs ${id && !idIsValid ? "text-danger" : "text-muted-foreground"}`}>
              {id && !idIsValid
                ? copy("Formato requerido: P seguido de 2 a 6 dígitos.", "Required format: P followed by 2 to 6 digits.")
                : copy("Ejemplo: P01. No escriba nombres ni documentos de identidad.", "Example: P01. Do not enter names or identity documents.")}
            </p>
          </div>
          <div><Label htmlFor="pdate">{copy("Fecha de inclusión", "Enrollment date")}</Label><Input id="pdate" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
          <div><Label htmlFor="psex">{copy("Sexo (opcional)", "Sex (optional)")}</Label><Input id="psex" value={sex} onChange={(e) => setSex(e.target.value)} /></div>
          <div><Label htmlFor="page">{copy("Grupo de edad (opcional)", "Age band (optional)")}</Label><Input id="page" value={ageBand} onChange={(e) => setAgeBand(e.target.value)} /></div>
          {err && <p className="text-sm text-danger">{err}</p>}
          <Button onClick={submit} disabled={busy || !idIsValid || !date} className="w-full">
            {busy ? copy("Guardando…", "Saving...") : mission ? copy("Crear con visitas V0–V7", "Create with V0–V7 visits") : copy("Crear participante", "Create participant")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
