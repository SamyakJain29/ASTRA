import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ASTRA — Tactical Space Operations Intelligence Platform",
  description: "Tactical CRT HUD ground station interface for spacecraft health monitoring, SGP4 orbital propagation, and anomaly detection.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-[#060c0b] text-[#e2e8f0] antialiased overflow-hidden font-mono">
        {children}
      </body>
    </html>
  );
}
