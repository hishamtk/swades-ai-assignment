import Link from "next/link";
import { VoiceRoom } from "@/components/VoiceRoom";

type Props = {
  searchParams: Promise<{ room?: string }>;
};

export default async function MonitorPage({ searchParams }: Props) {
  const params = await searchParams;
  const room = params.room;

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-12">
      <div>
        <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
          ← Home
        </Link>
        <h1 className="mt-4 text-2xl font-bold">Live Monitor</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Join an active call room to see transcript, agent state, take over, or
          read the post-call summary.
        </p>
      </div>
      <VoiceRoom mode="watcher" initialRoom={room} />
    </main>
  );
}
