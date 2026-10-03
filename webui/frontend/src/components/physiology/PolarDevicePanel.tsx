"use client";

import { Bluetooth, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { PolarConnection, PolarDevice } from "@/types/physiology";

export function PolarDevicePanel({ connection, devices, busy, locked, step, copy, onSearch, onConnect, onDisconnect }: {
  connection: PolarConnection; devices: PolarDevice[]; busy: boolean; locked: boolean;
  step: "searching" | "connecting" | "switching" | null;
  copy: (es: string, en: string) => string;
  onSearch: () => void; onConnect: (device: PolarDevice) => void; onDisconnect: () => void;
}) {
  const progress = step === "searching" ? copy("Buscando H10… (8 s)", "Searching for H10… (8 s)")
    : step === "connecting" ? copy("Conectando y comprobando la banda…", "Connecting and checking the strap…")
    : copy("Desconectando la banda anterior…", "Disconnecting the previous strap…");
  return <Card>
    <CardHeader>
      <CardTitle className="font-display text-xl uppercase tracking-wide">Polar H10 · {connection.connected ? copy("Conectado", "Connected") : copy("Conectar banda", "Connect strap")}</CardTitle>
      <CardDescription>{copy("Coloque y humedezca la banda de esta persona. Para identificarla la primera vez, mantenga las otras bandas inactivas.", "Fit and wet this participant’s strap. For first identification, keep the other straps inactive.")}</CardDescription>
    </CardHeader>
    <CardContent className="space-y-4">
      {connection.connected && <p className="font-semibold">{connection.device_alias} · {copy("lista para preparar la captura", "ready to prepare recording")}</p>}
      <Button className="h-auto min-h-10 whitespace-normal" disabled={busy || locked} onClick={onSearch}>
        {step ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Bluetooth className="mr-2 h-4 w-4" />}
        {step ? progress : connection.connected ? copy("Cambiar de banda", "Change strap") : copy("Buscar y conectar H10", "Find and connect H10")}
      </Button>
      {step && <p role="status" className="text-sm">{progress}</p>}
      {!connection.connected && !step && <p className="text-sm text-muted-foreground">{copy("Si aparece una sola banda disponible, se conecta automáticamente. Si aparecen varias, podrá elegir. La grabación comienza al pulsar Iniciar grabación.", "One available strap connects automatically. If several appear, you can choose. Recording begins when you press Start recording.")}</p>}
      {locked && !step && <p className="text-sm text-muted-foreground">{copy("Compruebe el estado y finalice la captura antes de cambiar de banda.", "Check status and finalize the recording before changing straps.")}</p>}
      {devices.map(device => <div key={device.device_token} className="space-y-2 rounded border border-white/10 p-3">
        <p className="font-semibold">{device.alias}</p>
        <p className="text-sm">{device.connectable === false
          ? copy("Visible, pero no acepta conexión. Cierre Polar Flow, Beat u otro receptor y vuelva a buscar.", "Visible but not accepting a connection. Close Polar Flow, Beat or another receiver, then search again.")
          : device.connectable === null ? copy("Detectada; se comprobará al conectar.", "Detected; availability will be checked on connection.") : copy("Disponible para conectar.", "Available to connect.")}</p>
        <Button variant="outline" disabled={busy || locked || connection.connected || device.connectable === false} onClick={() => onConnect(device)}>{copy("Conectar", "Connect")} {device.alias}</Button>
      </div>)}
      <details className="text-sm text-muted-foreground">
        <summary className="cursor-pointer">{copy("Ayuda de conexión y detalles", "Connection help and details")}</summary>
        <p className="mt-3">{copy("No necesita emparejar el H10 en la configuración de Windows ni escuchar HR emitida. Active Bluetooth y conecte desde esta pantalla. Si no aparece, retire y vuelva a colocar el sensor en la banda humedecida.", "You do not need to pair H10 in Windows settings or listen for broadcast HR. Enable Bluetooth and connect here. If it does not appear, detach and reattach the sensor to the wet strap.")}</p>
        <p className="mt-2">{copy("Los alias se mantienen durante esta ejecución del servicio; no son números de serie. No identifique a una persona por su pulso o por la intensidad de la señal.", "Aliases stay consistent during this service run; they are not serial numbers. Do not identify a person by pulse or signal strength.")}</p>
        {connection.capabilities && <p className="mt-2">{copy("Batería", "Battery")}: {connection.capabilities.battery_percent ?? "—"}% · Firmware {connection.capabilities.firmware ?? "—"}</p>}
        {connection.connected && <Button className="mt-3" size="sm" variant="outline" disabled={busy || locked} onClick={onDisconnect}>{copy("Desconectar", "Disconnect")}</Button>}
      </details>
    </CardContent>
  </Card>;
}
