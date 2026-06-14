"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUserContext } from "@/lib/user-context";

/**
 * Universal back-button. Defaults to a predictable destination based on the
 * current pathname:
 *   - phase pages (/free-agents, /options, /trade, /draft, /sim) → /team/{userTeam}
 *   - team page → /
 *   - awards/leaders → /team/{userTeam}
 *   - elsewhere → /
 *
 * Explicit `href` always wins. This avoids the "back button takes me to a
 * random place" problem that comes from relying on browser history.
 */
export function BackButton({ href, label }: { href?: string; label?: string }) {
  const pathname = usePathname();
  const { team } = useUserContext();
  const target = href ?? defaultBackHref(pathname ?? "/", team);
  const finalLabel = label ?? defaultBackLabel(pathname ?? "/", team);
  return (
    <Link
      href={target}
      className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-orange-400 mb-3"
    >
      ← {finalLabel}
    </Link>
  );
}

function defaultBackHref(pathname: string, team: string | null): string {
  if (pathname.startsWith("/team/")) return "/";
  if (
    pathname.startsWith("/free-agents") ||
    pathname.startsWith("/options") ||
    pathname.startsWith("/trade") ||
    pathname.startsWith("/draft") ||
    pathname.startsWith("/sim") ||
    pathname.startsWith("/awards") ||
    pathname.startsWith("/leaders")
  ) {
    return team ? `/team/${team}` : "/";
  }
  return "/";
}

function defaultBackLabel(pathname: string, team: string | null): string {
  if (pathname.startsWith("/team/")) return "Home";
  if (
    pathname.startsWith("/free-agents") ||
    pathname.startsWith("/options") ||
    pathname.startsWith("/trade") ||
    pathname.startsWith("/draft") ||
    pathname.startsWith("/sim") ||
    pathname.startsWith("/awards") ||
    pathname.startsWith("/leaders")
  ) {
    return team ? `Back to ${team}` : "Home";
  }
  return "Back";
}
