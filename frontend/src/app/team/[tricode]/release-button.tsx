"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export function ReleaseButton({ playerId, playerName }: { playerId: number; playerName: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const release = async () => {
    if (!confirm(`Release ${playerName} to free agency? Their contract will be deactivated.`)) return;
    setBusy(true);
    try {
      await api.releasePlayer(playerId);
      router.refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={release}
      disabled={busy}
      className="text-[10px] px-1.5 py-0.5 rounded border border-zinc-700 hover:bg-red-900/40 hover:border-red-700 text-zinc-500 hover:text-red-300 disabled:opacity-50"
      title="Waive this player to free agency"
    >
      {busy ? "…" : "Release"}
    </button>
  );
}
