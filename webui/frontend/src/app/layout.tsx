import { Suspense } from "react";
import type { Metadata } from "next";
import "./globals.css";
import { RouteShell } from "@/components/layout/RouteShell";
import { AppLocaleProvider } from "@/lib/i18n";
import { ConsoleProvider } from "@/lib/console-context";

export const metadata: Metadata = {
  title: "MATB-FAC",
  description: "Longitudinal Human Performance Lab",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-419" className="dark">
      <body className="font-sans antialiased">
        <AppLocaleProvider>
          <ConsoleProvider><RouteShell><Suspense>{children}</Suspense></RouteShell></ConsoleProvider>
        </AppLocaleProvider>
      </body>
    </html>
  );
}
