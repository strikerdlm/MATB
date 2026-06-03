"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createParticipant } from "@/lib/api";

export function AddParticipantDialog({ onCreated }: { onCreated: () => void }) {
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
      <DialogTrigger asChild><Button>Add participant</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Add participant</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label htmlFor="pid">ID (e.g. P01)</Label><Input id="pid" value={id} onChange={(e) => setId(e.target.value)} /></div>
          <div><Label htmlFor="pdate">Enrollment date</Label><Input id="pdate" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
          <div><Label htmlFor="psex">Sex (optional)</Label><Input id="psex" value={sex} onChange={(e) => setSex(e.target.value)} /></div>
          <div><Label htmlFor="page">Age band (optional)</Label><Input id="page" value={ageBand} onChange={(e) => setAgeBand(e.target.value)} /></div>
          {err && <p className="text-sm text-danger">{err}</p>}
          <Button onClick={submit} disabled={busy || !id || !date} className="w-full">
            {busy ? "Saving…" : "Create (generates 6 visits)"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
