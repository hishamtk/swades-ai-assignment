import Link from "next/link";

export default function HomePage() {
  const inboundPhone = process.env.NEXT_PUBLIC_INBOUND_PHONE_NUMBER;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-8 px-6 py-16">
      <header>
        <p className="text-sm font-medium text-[var(--accent)]">Swades Health</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">
          Voice Agent Hackathon
        </h1>
        <p className="mt-3 text-[var(--muted)]">
          Agent A handles appointments, live monitoring, watcher takeover, and
          warm transfer to a human via Twilio SIP.
        </p>
      </header>

      {inboundPhone && (
        <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
            Call by Phone
          </h2>
          <p className="mt-2 text-2xl font-mono font-semibold">{inboundPhone}</p>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Dial this number to reach Agent A via PSTN (Twilio → LiveKit SIP).
          </p>
        </section>
      )}

      <nav className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link
          href="/call"
          className="rounded-xl border border-[var(--accent)]/40 bg-[var(--card)] p-6 transition hover:border-[var(--accent)]"
        >
          <h2 className="text-lg font-semibold">Start Web Call</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Talk to Agent A from your browser microphone — good for local testing.
          </p>
        </Link>
        <Link
          href="/monitor"
          className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6 transition hover:border-[var(--accent)]/40"
        >
          <h2 className="text-lg font-semibold">Monitor Dashboard</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Watch live transcript and agent state, take over the call, view summary.
          </p>
        </Link>
        <Link
          href="/appointments"
          className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6 transition hover:border-[var(--accent)]/40 sm:col-span-2 lg:col-span-1"
        >
          <h2 className="text-lg font-semibold">Appointments</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            View all bookings created by Agent A — name, time, reason, and contact.
          </p>
        </Link>
      </nav>

      <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 text-sm text-[var(--muted)]">
        <h2 className="font-semibold text-[var(--foreground)]">Quick start</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5">
          <li>Copy <code>.env.example</code> → <code>.env</code> and <code>frontend/.env.local</code></li>
          <li>Backend: <code>cd backend && pip install -r requirements.txt && python agent.py dev</code></li>
          <li>Frontend: <code>cd frontend && npm install && npm run dev</code></li>
        </ol>
      </section>
    </main>
  );
}
