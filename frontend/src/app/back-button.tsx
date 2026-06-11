"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

/**
 * Universal back-button used in the top-left of pages.
 * Falls back to a Link if `href` is provided; otherwise uses router.back().
 */
export function BackButton({ href, label = "Back" }: { href?: string; label?: string }) {
  const router = useRouter();
  if (href) {
    return (
      <Link
        href={href}
        className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-orange-400 mb-3"
      >
        ← {label}
      </Link>
    );
  }
  return (
    <button
      onClick={() => router.back()}
      className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-orange-400 mb-3"
    >
      ← {label}
    </button>
  );
}
