"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export function ResetButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const onClick = async () => {
    if (!confirm("Reset the entire game to the 2026-27 offseason starting state? All trades, signings, draft picks, and sim results will be wiped.")) return;
    setBusy(true);
    try {
      await api.reset();
      router.refresh();
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className="px-3 py-1.5 text-sm rounded border border-zinc-700 hover:bg-zinc-800 disabled:opacity-50"
    >
      {busy ? "Resetting…" : "↻ Reset Game"}
    </button>
  );
}
