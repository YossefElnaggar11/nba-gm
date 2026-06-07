import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { NavQuickLinks, NavUserBadge } from "./nav-user-badge";

export const metadata: Metadata = {
  title: "NBA GM 2026",
  description: "Be the GM of your favorite NBA team starting from the 2026 offseason.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-100 font-sans">
        <header className="border-b border-zinc-800 bg-zinc-900/60 backdrop-blur sticky top-0 z-10">
          <nav className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-6">
            <Link href="/" className="font-bold text-lg tracking-tight">
              NBA GM <span className="text-orange-400">2026</span>
            </Link>
            <NavQuickLinks />
            <NavUserBadge />
          </nav>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-zinc-800 py-3 px-6 text-xs text-zinc-500 text-center">
          NBA GM 2026 · Data from Basketball-Reference, Spotrac, NBA.com · Built for fun
        </footer>
      </body>
    </html>
  );
}
