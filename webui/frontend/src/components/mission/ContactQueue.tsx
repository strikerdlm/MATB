"use client";

import React from "react";
import type { ContactSnapshot, Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { Button } from "@/components/ui/button";

interface ContactQueueProps {
  contacts: ContactSnapshot[];
  locale: Locale;
  selectedContactId?: string | null;
  onInspect: (contact: ContactSnapshot) => void;
  onSelect: (contactId: string) => void;
  readOnly?: boolean;
}
const workflowRank: Record<ContactSnapshot["workflow"], number> = { DETECTED: 0, INSPECTED: 1, CLASSIFIED: 2, PRIORITIZED: 3, REPORTED: 4, UNDETECTED: 9 };
export function sortContacts(contacts: ContactSnapshot[]) { return [...contacts].filter((contact) => contact.evidence !== "NONE").sort((left, right) => workflowRank[left.workflow] - workflowRank[right.workflow] || left.contact_id.localeCompare(right.contact_id)); }
export function ContactQueue({ contacts, locale, selectedContactId = null, onInspect, onSelect, readOnly = false }: ContactQueueProps) {
  return <section aria-labelledby="mission-contact-heading" className="flex min-h-0 flex-1 flex-col"><div className="border-b border-white/10 px-4 py-3"><div className="page-kicker">{t(locale, "mission.evidence")} / {contacts.filter((contact) => contact.evidence !== "NONE").length.toString().padStart(2, "0")}</div><h2 id="mission-contact-heading" className="mt-1 font-display text-lg uppercase tracking-wide">{t(locale, "mission.contacts")}</h2></div><ol className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">{sortContacts(contacts).map((contact) => { const inspectable = contact.evidence === "INSPECTABLE" && ["DETECTED", "INSPECTED"].includes(contact.workflow); const selected = selectedContactId === contact.contact_id; return <li key={contact.contact_id} className={`rounded border p-3 ${selected ? "border-info bg-info/10" : "border-white/10 bg-black/15"}`}><div className="flex items-center justify-between gap-2"><span className="font-mono text-sm font-semibold">{contact.contact_id}</span><span className="font-mono text-[10px] uppercase text-warning">{t(locale, `contact.workflow_${contact.workflow.toLowerCase()}` as never)}</span></div><div className="mt-2 flex flex-wrap gap-1"><Button type="button" size="sm" variant={selected ? "default" : "outline"} aria-pressed={selected} onClick={() => onSelect(contact.contact_id)}>{selected ? (locale === "es-CO" ? "Seleccionado" : "Selected") : t(locale, "a11y.select_contact", { contact: contact.contact_id })}</Button>{inspectable && <Button type="button" size="sm" variant="outline" disabled={readOnly} onClick={() => onInspect(contact)}>{t(locale, "contact.inspect", { contact: contact.contact_id })}</Button>}</div></li>; })}</ol></section>;
}
