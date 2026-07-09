import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RevenueOps Control Plane",
  description: "Hourly profile intelligence that proves which presentation changes increase client intent.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="grid-bg min-h-screen">{children}</body>
    </html>
  );
}
