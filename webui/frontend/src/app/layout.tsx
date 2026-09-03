import type { Metadata } from "next";
import "./globals.css";
import { RouteShell } from "@/components/layout/RouteShell";
import { AppLocaleProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "MATB-FAC",
  description: "Longitudinal Human Performance Lab",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-419" className="dark">
      <body className="font-sans antialiased">
        <AppLocaleProvider>
          <RouteShell>{children}</RouteShell>
        </AppLocaleProvider>
      </body>
    </html>
  );
}
