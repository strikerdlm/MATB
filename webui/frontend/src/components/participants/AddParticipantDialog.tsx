"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createParticipant } from "@/lib/api";
import { useAppLocale } from "@/lib/i18n";

export function AddParticipantDialog({ onCreated }: { onCreated: () => void }) {
  const { copy } = useAppLocale();
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [date, setDate] = useState("");
  const [sex, setSex] = useState("");
  const [ageBand, setAgeBand] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      await createParticipant({ id, enrollment_date: date, sex: sex || undefined, age_band: ageBand || undefined });
      setOpen(false); setId(""); setDate(""); setSex(""); setAgeBand("");
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
          <div><Label htmlFor="pid">{copy("ID (p. ej., P01)", "ID (e.g. P01)")}</Label><Input id="pid" value={id} onChange={(e) => setId(e.target.value)} /></div>
          <div><Label htmlFor="pdate">{copy("Fecha de inclusión", "Enrollment date")}</Label><Input id="pdate" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
          <div><Label htmlFor="psex">{copy("Sexo (opcional)", "Sex (optional)")}</Label><Input id="psex" value={sex} onChange={(e) => setSex(e.target.value)} /></div>
          <div><Label htmlFor="page">{copy("Grupo de edad (opcional)", "Age band (optional)")}</Label><Input id="page" value={ageBand} onChange={(e) => setAgeBand(e.target.value)} /></div>
          {err && <p className="text-sm text-danger">{err}</p>}
          <Button onClick={submit} disabled={busy || !id || !date} className="w-full">
            {busy ? copy("Guardando…", "Saving...") : copy("Crear (genera visitas T0, DM8 y DM15)", "Create (generates T0, DM8, and DM15 visits)")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
