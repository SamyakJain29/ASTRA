import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ASTRA — Space Operations Intelligence Platform",
  description: "Spacecraft health monitoring, backend-propagated SGP4 orbital awareness, and Adaptive Event Memory operations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className="bg-[#020706] text-[#e2e8f0] antialiased overflow-hidden font-mono"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
