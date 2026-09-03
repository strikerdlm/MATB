"use client";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { Locale as SimulationLocale } from "@/types/simulation";

export type AppLocale = "es-419" | "en";

const EN = {
  "brand.console": "Research console",
  "brand.lab": "Longitudinal Human Performance Lab",
  "brand.author": "Author: Diego L Malpica H - ASTRA - DIMAE",
  "shell.mode": "Mode",
  "shell.operations": "Operations",
  "shell.link": "Link",
  "shell.live": "Live",
  "language.label": "Language",
  "language.spanish": "Español latinoamericano",
  "language.english": "English",
  "nav.tracker": "Tracker",
  "nav.designer": "Designer",
  "nav.participants": "Participants",
  "nav.upload": "Upload",
  "nav.visualization": "Visualization",
  "nav.analysis": "Analysis",
  "nav.screen": "Screen",
  "nav.liftoff": "Liftoff",
  "nav.mission": "Research mission",
  "nav.tests": "MATB-FAC tests",
  "nav.openmatb": "Classic OpenMATB",
  "nav.soon": "soon",
  "nav.coming_soon": "Coming soon",
  "common.loading": "Loading…",
  "common.error": "Could not load the requested information.",
  "technical.kicker": "Interactive technical mode",
  "technical.title": "MATB-FAC tests",
  "technical.subtitle": "Launch one programmed profile directly from the frontend.",
  "technical.scenario": "Scenario",
  "technical.profile": "Workload profile",
  "technical.duration": "Configured duration",
  "technical.fleet": "Aircraft",
  "technical.calibration": "Calibration status",
  "technical.pending_calibration": "Engineering preset pending independent human calibration",
  "technical.practice": "Practice",
  "technical.low": "Low",
  "technical.medium": "Medium",
  "technical.high": "High",
  "technical.start": "Launch interactive test",
  "technical.starting": "Preparing test…",
  "technical.acknowledgement": "I understand this is a technical interactive test and not a valid participant session.",
  "technical.acknowledgement_required": "Confirm the technical-use notice before launch.",
  "technical.notice": "Technical-only run. It is excluded from participant analyses and scientific exports.",
  "technical.no_scenarios": "No valid scenarios are installed.",
  "technical.mode_badge": "TECHNICAL MODE",
  "technical.not_participant_data": "Not eligible for participant analysis",
} as const;

const ES_419: Record<keyof typeof EN, string> = {
  "brand.console": "Consola de investigación",
  "brand.lab": "Longitudinal Human Performance Lab",
  "brand.author": "Author: Diego L Malpica H - ASTRA - DIMAE",
  "shell.mode": "Modo",
  "shell.operations": "Operaciones",
  "shell.link": "Enlace",
  "shell.live": "Activo",
  "language.label": "Idioma",
  "language.spanish": "Español latinoamericano",
  "language.english": "English",
  "nav.tracker": "Seguimiento",
  "nav.designer": "Diseñador",
  "nav.participants": "Participantes",
  "nav.upload": "Cargar datos",
  "nav.visualization": "Visualización",
  "nav.analysis": "Análisis",
  "nav.screen": "Pruebas cognitivas",
  "nav.liftoff": "Liftoff",
  "nav.mission": "Misión de investigación",
  "nav.tests": "Pruebas MATB-FAC",
  "nav.openmatb": "OpenMATB clásico",
  "nav.soon": "pronto",
  "nav.coming_soon": "Próximamente",
  "common.loading": "Cargando…",
  "common.error": "No se pudo cargar la información solicitada.",
  "technical.kicker": "Modo técnico interactivo",
  "technical.title": "Pruebas MATB-FAC",
  "technical.subtitle": "Inicie directamente desde la interfaz uno de los perfiles programados.",
  "technical.scenario": "Escenario",
  "technical.profile": "Perfil de carga",
  "technical.duration": "Duración configurada",
  "technical.fleet": "Aeronaves",
  "technical.calibration": "Estado de calibración",
  "technical.pending_calibration": "Preajuste de ingeniería pendiente de calibración humana independiente",
  "technical.practice": "Práctica",
  "technical.low": "Baja",
  "technical.medium": "Media",
  "technical.high": "Alta",
  "technical.start": "Iniciar prueba interactiva",
  "technical.starting": "Preparando prueba…",
  "technical.acknowledgement": "Entiendo que esta es una prueba técnica interactiva y no una sesión válida de participante.",
  "technical.acknowledgement_required": "Confirme el aviso de uso técnico antes de iniciar.",
  "technical.notice": "Ejecución exclusivamente técnica. Se excluye de los análisis de participantes y de las exportaciones científicas.",
  "technical.no_scenarios": "No hay escenarios válidos instalados.",
  "technical.mode_badge": "MODO TÉCNICO",
  "technical.not_participant_data": "No apto para análisis de participantes",
};

export type AppTranslationKey = keyof typeof EN;

interface AppLocaleContextValue {
  locale: AppLocale;
  simulationLocale: SimulationLocale;
  setLocale: (locale: AppLocale) => void;
  tr: (key: AppTranslationKey) => string;
  copy: (spanish: string, english: string) => string;
}

const AppLocaleContext = createContext<AppLocaleContextValue>({
  locale: "en",
  simulationLocale: "en",
  setLocale: () => undefined,
  tr: (key) => EN[key],
  copy: (_spanish, english) => english,
});
const STORAGE_KEY = "matb-fac.locale";

export function AppLocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>("es-419");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "es-419") setLocaleState(stored);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<AppLocaleContextValue>(() => ({
    locale,
    simulationLocale: locale === "en" ? "en" : "es-CO",
    setLocale: (next) => {
      setLocaleState(next);
      window.localStorage.setItem(STORAGE_KEY, next);
    },
    tr: (key) => (locale === "en" ? EN[key] : ES_419[key]),
    copy: (spanish, english) => (locale === "en" ? english : spanish),
  }), [locale]);

  return <AppLocaleContext.Provider value={value}>{children}</AppLocaleContext.Provider>;
}

export function useAppLocale(): AppLocaleContextValue {
  return useContext(AppLocaleContext);
}
