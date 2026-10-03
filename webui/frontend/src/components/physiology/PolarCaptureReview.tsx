"use client";

import { useEffect, useState } from "react";
import { EChart } from "@/components/charts/EChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { downloadPolarRRFile, getPolarReview, getPolarRRExport } from "@/lib/physiology/api";
import type { PolarCapture, PolarReview, PolarRRExport } from "@/types/physiology";

type Copy = (es: string, en: string) => string;

function lineOption(data: Array<[number, number | null]>, x: string, y: string) {
  return {
    animation: false, tooltip: { trigger: "axis" },
    grid: { left: 65, right: 25, top: 25, bottom: 65 },
    xAxis: { type: "value", name: x, nameLocation: "middle", nameGap: 35 },
    yAxis: { type: "value", name: y, scale: true },
    dataZoom: [{ type: "inside" }],
    series: [{ type: "line", data, showSymbol: false, connectNulls: false, lineStyle: { width: 1.5, color: "#136f86" } }],
  };
}

export function PolarCaptureReview({ capture, lease, copy }: { capture: PolarCapture; lease: string; copy: Copy }) {
  const [rr, setRR] = useState<PolarRRExport | null>(null);
  const [review, setReview] = useState<PolarReview | null>(null);
  const [failure, setFailure] = useState(false);
  const [retry, setRetry] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);
  const finalized = ["finalized", "incomplete"].includes(capture.artifact_state);

  useEffect(() => {
    if (!finalized || !lease) return;
    let active = true;
    setFailure(false);
    setRR(null);
    setReview(null);
    void getPolarRRExport(capture.capture_id, lease).then((value) => { if (active) setRR(value); })
      .catch(() => { if (active) setFailure(true); });
    void getPolarReview(capture.capture_id, lease).then((value) => { if (active) setReview(value); })
      .catch(() => { if (active) setFailure(true); });
    return () => { active = false; };
  }, [capture.capture_id, finalized, lease, retry]);

  async function download(filename: string) {
    setDownloading(true);
    setDownloadError(false);
    try { await downloadPolarRRFile(capture.capture_id, lease, filename); }
    catch { setDownloadError(true); }
    finally { setDownloading(false); }
  }

  if (!finalized) return null;
  const metrics = review?.metrics;
  const respiration = review?.respiration;
  const traceFile = rr?.files.find((file) => file.kind === "trace_csv");
  return <div className="space-y-6">
    {failure && <p role="status" className="text-sm">{copy("La captura está guardada. Puede volver a cargar la revisión y las descargas.", "The capture is saved. You can reload the review and downloads.")} <Button variant="outline" size="sm" onClick={() => setRetry((value) => value + 1)}>{copy("Volver a cargar", "Reload")}</Button></p>}
    {rr && <Card>
      <CardHeader><CardTitle>{copy("Intervalos RR (ms)", "RR intervals (ms)")}</CardTitle>
        <CardDescription>{copy("Intervalos originales transmitidos por el Polar. Un valor por latido, sin corrección ni interpolación.", "Original intervals transmitted by Polar. One value per beat, without correction or interpolation.")}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <p>{rr.rr_count} {copy("intervalos", "intervals")} · {rr.segment_count} {copy("tramos continuos", "continuous segments")} · {rr.execution_purpose === "practice" ? copy("Práctica", "Practice") : copy("Estudio", "Study")}</p>
        {rr.segment_count > 1 && <p className="text-sm">{copy("Las interrupciones separan los archivos. Analice cada tramo por separado en Kubios.", "Interruptions split the files. Analyze each segment separately in Kubios.")}</p>}
        {rr.excluded_nonpositive_or_nonfinite > 0 && <p className="text-sm">{rr.excluded_nonpositive_or_nonfinite} {copy("valores no positivos o no finitos permanecen en el CSV completo; se excluyen de los archivos RR.", "nonpositive or nonfinite values remain in the full CSV and are excluded from RR files.")}</p>}
        {rr.contact_not_detected_count > 0 && <p className="text-sm">{copy("Hay intervalos sin contacto confirmado. El CSV completo conserva estas marcas para revisar la señal.", "Some intervals lack confirmed contact. The full CSV retains these flags for signal review.")}</p>}
        {rr.incomplete_reasons.length > 0 && <p className="text-sm">{copy("Registro incompleto: revise las interrupciones antes de analizarlo.", "Incomplete recording: review interruptions before analysis.")}</p>}
        <div className="flex flex-wrap gap-2">{rr.segments.map((segment) => <div key={segment.segment_id} className="flex flex-wrap items-center gap-2 border border-white/10 p-3">
          <span className="text-sm">{copy("Tramo", "Segment")} {segment.segment_id} · {segment.rr_count} RR</span>
          <Button size="sm" variant="outline" disabled={downloading} onClick={() => void download(segment.txt_filename)}>TXT Kubios · ms</Button>
          <Button size="sm" variant="outline" disabled={downloading} onClick={() => void download(segment.csv_filename)}>CSV RR · ms</Button>
        </div>)}</div>
        <div className="flex flex-wrap gap-2">
          {traceFile && <Button variant="outline" size="sm" disabled={downloading} onClick={() => void download(traceFile.filename)}>{copy("CSV completo con tiempos y calidad", "Full CSV with timing and quality")}</Button>}
          <Button variant="outline" size="sm" disabled={downloading} onClick={() => void download("rr_export_manifest.json")}>{copy("Metadatos de exportación", "Export metadata")}</Button>
          <Button variant="outline" size="sm" disabled={downloading} onClick={() => void download("capture_context.json")}>{copy('Participante, sesión y marcas', 'Participant, session and markers')}</Button>
        </div>
        {downloadError && <p role="alert">{copy("No se pudo descargar el archivo. Vuelva a pulsar su botón de descarga.", "Could not download the file. Press its download button to retry.")}</p>}
        {rr.rr_count > 0 && <>
          <p className="text-sm text-muted-foreground">{copy("En Kubios: tipo RR, unidades ms, columna 1. TXT: 0 líneas de encabezado; CSV RR: 1. Sin columna de tiempo.", "In Kubios: RR data, ms units, column 1. TXT: 0 header lines; RR CSV: 1. No time column.")}</p>
          <details><summary className="cursor-pointer text-sm">{copy("Ver los primeros intervalos", "View the first intervals")} ({rr.preview.length})</summary>
            <div className="mt-3 max-h-56 overflow-auto"><table className="w-full text-sm"><thead><tr><th>{copy("Latido", "Beat")}</th><th>RR (ms)</th><th>{copy("Tramo", "Segment")}</th></tr></thead><tbody>{rr.preview.map((sample) => <tr key={sample.beat_index}><td className="text-center">{sample.beat_index}</td><td className="text-center font-mono">{sample.rr_ms.toFixed(3)}</td><td className="text-center">{sample.segment_id}</td></tr>)}</tbody></table></div>
          </details>
        </>}
      </CardContent>
    </Card>}
    {review && <Card>
      <CardHeader><CardTitle>{copy("Revisión de la señal capturada", "Captured signal review")}</CardTitle>
        <CardDescription>{copy("Cálculos locales a partir de los datos guardados. Valores descriptivos, sin puntuación de recuperación ni clasificación clínica.", "Local calculations from saved data. Descriptive values without a recovery score or clinical classification.")}</CardDescription></CardHeader>
      <CardContent className="space-y-5">
        <p className="text-sm text-muted-foreground">{copy('Vista rápida: últimos cinco minutos del tramo continuo más largo, o ventana corta disponible. Para el basal ASTRA, revise el primer segmento prescrito de cinco minutos; esta vista no lo selecciona automáticamente.', 'Quick view: last five minutes of the longest continuous segment, or the available short window. For the ASTRA baseline, review the first prescribed five-minute segment; this view does not select it automatically.')}</p>
        {metrics && <p className="text-sm">{copy("Ventana analizada", "Analysis window")}: {metrics.duration_s.toFixed(1)} s · {metrics.window_kind === "five_minute" ? copy("cinco minutos", "five minutes") : copy("ventana corta exploratoria", "exploratory short window")}</p>}
        {metrics?.valid && <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[
          ["HR", metrics.mean_instantaneous_hr_bpm, "bpm"], ["RMSSD", metrics.rmssd_ms, "ms"],
          ["SDNN", metrics.sdnn_ms, "ms"], ["pNN50", metrics.pnn50_percent, "%"],
        ].map(([name, value, unit]) => typeof value === "number" && <div key={String(name)} className="metric-tile"><p className="page-kicker">{name}</p><p className="mt-2 font-display text-2xl">{value.toFixed(1)} <span className="text-sm">{unit}</span></p></div>)}</div>}
        <div className="grid gap-4 lg:grid-cols-2">
          {metrics?.sqi != null && <EChart height={240} option={{ animation: false, xAxis: [], yAxis: [], series: [{ type: "gauge", min: 0, max: 100, startAngle: 180, endAngle: 0, center: ["50%", "75%"], radius: "90%", progress: { show: true, width: 14 }, axisLine: { lineStyle: { width: 14, color: [[1, "#dbe5e8"]] } }, itemStyle: { color: "#136f86" }, pointer: { show: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, detail: { formatter: "{value}%", offsetCenter: [0, "-20%"], fontSize: 24 }, title: { offsetCenter: [0, "15%"], fontSize: 12 }, data: [{ value: Number((100 * metrics.sqi).toFixed(1)), name: copy("RR aceptados · calidad de señal", "Accepted RR · signal quality") }] }] }} />}
          {review.rr_tachogram.length > 0 && <EChart height={270} option={lineOption(review.rr_tachogram, copy("Tiempo (s)", "Time (s)"), "RR (ms)")} />}
          {metrics?.valid && review.poincare.length > 0 && <EChart height={270} option={{ animation: false, tooltip: { trigger: "item" }, grid: { left: 65, right: 25, bottom: 65 }, xAxis: { type: "value", name: "RR n (ms)", nameLocation: "middle", nameGap: 35, scale: true }, yAxis: { type: "value", name: "RR n+1 (ms)", scale: true }, series: [{ type: "scatter", symbolSize: 4, data: review.poincare, itemStyle: { color: "#136f86" } }] }} />}
          {metrics?.spectrum && <EChart height={270} option={lineOption(metrics.spectrum, copy("Frecuencia (Hz)", "Frequency (Hz)"), "PSD (ms²/Hz)")} />}
        </div>
        {respiration?.status === "estimated" && <div className="space-y-3 border-t border-white/10 pt-4">
          <h3 className="font-semibold">{copy("Frecuencia respiratoria estimada · experimental", "Estimated respiratory rate · experimental")}</h3>
          <p className="font-display text-3xl">{respiration.respiratory_rate_bpm?.toFixed(1)} <span className="text-base">resp/min</span></p>
          <p className="text-sm text-muted-foreground">{copy("Estimación del movimiento torácico en los ejes de aceleración. Exactitud frente a una referencia respiratoria aún no validada.", "Estimated from chest motion in the acceleration axes. Accuracy against a respiratory reference has not yet been validated.")} {respiration.accepted_windows}/{respiration.evaluated_windows} {copy("ventanas aceptadas", "accepted windows")}.</p>
          <div className="grid gap-4 lg:grid-cols-2">
            <EChart height={250} option={lineOption(respiration.windows.map((window) => [window.time_s, window.rate_bpm]), copy("Tiempo (s)", "Time (s)"), "resp/min")} />
            <EChart height={250} option={lineOption(respiration.waveform, copy("Tiempo (s)", "Time (s)"), copy("ACC filtrada (mg)", "Filtered ACC (mg)"))} />
          </div>
        </div>}
      </CardContent>
    </Card>}
  </div>;
}
