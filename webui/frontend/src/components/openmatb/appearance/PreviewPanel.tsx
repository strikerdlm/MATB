import type { ReactNode } from "react";

export function PreviewPanel({
  title,
  children,
  className = "",
  headerColor,
  headerText,
  borderColor,
  radius,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  headerColor: string;
  headerText: string;
  borderColor: string;
  radius: number;
}) {
  return (
    <section className={`fac-panel ${className}`} style={{ borderColor, borderRadius: radius }}>
      <div className="fac-panel-title" style={{ background: headerColor, color: headerText, borderColor }}>{title}</div>
      <div className="fac-panel-body">{children}</div>
    </section>
  );
}
