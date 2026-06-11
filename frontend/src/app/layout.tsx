import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "./nav-user-badge";

export const metadata: Metadata = {
  title: "NBA GM 2026",
  description: "Be the GM of your favorite NBA team starting from the 2026 offseason.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-100 font-sans">
        <NavBar />
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
