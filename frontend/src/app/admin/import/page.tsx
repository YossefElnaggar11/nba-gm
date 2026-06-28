"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { BackButton } from "@/app/back-button";

const SAMPLE = `{
  "draft": [
    {"pick": 1, "team": "WAS", "player": "Cooper Flagg",
     "college": "Duke", "age": 18, "position": "F", "overall": 88, "potential": 95},
    {"pick": 2, "team": "SAS", "player": "Dylan Harper",
     "college": "Rutgers", "age": 19, "position": "G", "overall": 82, "potential": 91}
  ],
  "trades": [
    {
      "description": "Giannis to HOU (2026-06-26)",
      "legs": [
        {"team": "MIL", "out_players": ["Giannis Antetokounmpo"], "out_picks": []},
        {"team": "HOU", "out_players": ["Alperen Şengün", "Reed Sheppard"], "out_picks": ["2027:1:HOU", "2029:1:HOU"]}
      ]
    }
  ],
  "signings": [
    {"player": "LeBron James", "team": "LAL",
     "salary_year1": 52628571, "years": 2, "using": "BIRD"}
  ]
}`;

export default function ImportEventsPage() {
  const [text, setText] = useState("");
  const [merge, setMerge] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState<unknown>(null);

  const loadExisting = async () => {
    try {
      const e = await api.getEvents();
      setExisting(e);
    } catch (err) {
      setError(`Failed to load existing events: ${String(err)}`);
    }
  };
  useEffect(() => { loadExisting(); }, []);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const payload = JSON.parse(text);
      payload.merge = merge;
      const r = await api.importEvents(payload);
      setResult(r);
      await loadExisting();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <BackButton />
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Import Real-World Events</h1>
        <p className="text-zinc-400 mt-1 max-w-3xl">
          Apply real 2026 NBA Draft picks, trades, and free-agent signings on top of the seeded
          rosters. Whatever you submit here is saved to disk and re-applied on every reset/redeploy.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input side */}
        <div className="space-y-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold">Paste JSON</h2>
              <button
                onClick={() => setText(SAMPLE)}
                className="text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
              >
                Load sample
              </button>
            </div>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder='{"draft":[...], "trades":[...], "signings":[...]}'
              className="w-full h-[420px] bg-zinc-950 border border-zinc-700 rounded p-3 text-xs font-mono text-zinc-200"
              spellCheck={false}
            />
            <label className="flex items-center gap-2 mt-3 text-sm text-zinc-400 cursor-pointer">
              <input
                type="checkbox"
                checked={merge}
                onChange={e => setMerge(e.target.checked)}
                className="accent-orange-500"
              />
              <span>
                Merge with existing events
                <span className="ml-1 text-xs text-zinc-600">
                  (uncheck to fully replace)
                </span>
              </span>
            </label>
            <button
              onClick={submit}
              disabled={busy || !text.trim()}
              className="mt-3 w-full px-4 py-2 rounded-md bg-orange-500 hover:bg-orange-400 text-black font-semibold disabled:opacity-50"
            >
              {busy ? "Applying…" : "Apply events"}
            </button>
            {error && (
              <div className="mt-3 p-3 rounded border border-red-800 bg-red-900/20 text-red-300 text-sm whitespace-pre-line">
                {error}
              </div>
            )}
          </div>

          <details className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <summary className="cursor-pointer font-semibold text-sm">Schema reference</summary>
            <div className="mt-3 text-xs text-zinc-400 space-y-3 leading-relaxed">
              <div>
                <div className="text-zinc-200 font-semibold mb-1">Draft pick</div>
                <code className="text-zinc-300">{`{pick: number, team: "TRI", player: "name", college?, age?, position?, overall?, potential?}`}</code>
                <p className="text-zinc-500 mt-1">
                  If <code>team</code> differs from the slot&apos;s current owner (e.g. draft-day trade),
                  the slot is reassigned. If <code>player</code> isn&apos;t in our prospect list, a new
                  Prospect is created from your fields.
                </p>
              </div>
              <div>
                <div className="text-zinc-200 font-semibold mb-1">Trade (2-team, simple)</div>
                <code className="text-zinc-300">{`{description, legs: [{team, out_players: [name], out_picks: ["YEAR:RD" or "YEAR:RD:ORIG"]}]}`}</code>
                <p className="text-zinc-500 mt-1">
                  Pick spec: <code>2027:1</code> means a 2027 first-rounder originally from
                  the leg&apos;s team. <code>2027:1:HOU</code> means a 2027 1st that originated
                  from HOU. Assets default-route to the other team.
                </p>
              </div>
              <div>
                <div className="text-zinc-200 font-semibold mb-1">Trade (3+ team)</div>
                <code className="text-zinc-300">{`legs[i].out_players_routed: [{player, to: "TRI"}], out_picks_routed: [{pick, to}]`}</code>
              </div>
              <div>
                <div className="text-zinc-200 font-semibold mb-1">Signing</div>
                <code className="text-zinc-300">{`{player, team, salary_year1, years, using?, first_season?, contract_seasons?}`}</code>
                <p className="text-zinc-500 mt-1">
                  Either use <code>salary_year1 + years</code> with auto-raises, or supply
                  the full <code>contract_seasons: [{`{season, salary, option_type?}`}]</code> list.
                </p>
              </div>
            </div>
          </details>
        </div>

        {/* Result + current state side */}
        <div className="space-y-4">
          {result !== null && (
            <div className="bg-emerald-900/10 border border-emerald-700 rounded-lg p-4">
              <h2 className="font-semibold text-emerald-300 mb-2">✓ Applied</h2>
              <pre className="text-xs text-zinc-300 overflow-auto max-h-80 bg-zinc-950 p-3 rounded">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}

          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-semibold">Currently persisted</h2>
              <button onClick={loadExisting} className="text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700">
                ↻ Reload
              </button>
            </div>
            <pre className="text-xs text-zinc-400 overflow-auto max-h-[420px] bg-zinc-950 p-3 rounded">
              {existing ? JSON.stringify(existing, null, 2) : "Loading…"}
            </pre>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 text-xs text-zinc-400 leading-relaxed">
            <p>
              <strong className="text-zinc-200">After importing:</strong> open{" "}
              <Link href="/team/WAS" className="text-orange-400 hover:underline">a team page</Link>{" "}
              or the{" "}
              <Link href="/draft/2026" className="text-orange-400 hover:underline">2026 draft list</Link>{" "}
              to verify the picks landed correctly.
            </p>
            <p className="mt-2">
              Changes survive Render redeploys (the events file is part of the repo).
              To start fresh, post <code className="text-zinc-300">{`{ "merge": false, "draft": [], "trades": [], "signings": [] }`}</code>.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
