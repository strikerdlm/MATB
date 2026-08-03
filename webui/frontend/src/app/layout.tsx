import type { Metadata } from "next";
import "./globals.css";
import { RouteShell } from "@/components/layout/RouteShell";

export const metadata: Metadata = {
  title: "MATB Research Console",
  description: "Longitudinal MATB study tracker",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans antialiased">
        <RouteShell>{children}</RouteShell>
      </body>
    </html>
  );
}
