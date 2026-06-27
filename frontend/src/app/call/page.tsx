import Link from "next/link";
import { VoiceRoom } from "@/components/VoiceRoom";

export default function CallPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <div>
        <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
          ← Home
        </Link>
        <h1 className="mt-4 text-2xl font-bold">Call Agent A</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Starts a new LiveKit room and dispatches the Python voice agent.
        </p>
      </div>
      <VoiceRoom mode="caller" />
    </main>
  );
}
