import Link from "next/link";
import { AppointmentsList } from "@/components/AppointmentsList";

export default function AppointmentsPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-6 py-12">
      <div>
        <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
          ← Home
        </Link>
        <h1 className="mt-4 text-2xl font-bold">Appointments</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Appointments booked by Agent A during phone and web calls.
        </p>
      </div>
      <AppointmentsList />
    </main>
  );
}
