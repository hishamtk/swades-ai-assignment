"use client";

import { useCallback, useEffect, useState } from "react";
import type { AppointmentRecord } from "@/app/api/appointments/route";

export function AppointmentsList() {
  const [appointments, setAppointments] = useState<AppointmentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/appointments");
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error ?? "Failed to load appointments");
      }
      setAppointments(data.appointments ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load appointments");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, [load]);

  if (loading) {
    return (
      <p className="text-sm text-[var(--muted)]">Loading appointments…</p>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/40 bg-[var(--card)] p-4">
        <p className="text-sm text-red-400">{error}</p>
        <button
          type="button"
          onClick={load}
          className="mt-3 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  if (appointments.length === 0) {
    return (
      <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6">
        <p className="text-sm text-[var(--muted)]">
          No appointments yet. Book one by calling Agent A on the phone or web.
        </p>
      </section>
    );
  }

  return (
    <section className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)]">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-[var(--muted)]">
              <th className="px-4 py-3 font-semibold uppercase tracking-wide">
                Patient
              </th>
              <th className="px-4 py-3 font-semibold uppercase tracking-wide">
                Appointment
              </th>
              <th className="px-4 py-3 font-semibold uppercase tracking-wide">
                Reason
              </th>
              <th className="px-4 py-3 font-semibold uppercase tracking-wide">
                Phone
              </th>
              <th className="px-4 py-3 font-semibold uppercase tracking-wide">
                Booked
              </th>
            </tr>
          </thead>
          <tbody>
            {appointments.map((appt) => (
              <tr
                key={appt.id}
                className="border-b border-[var(--border)] last:border-0"
              >
                <td className="px-4 py-3 font-medium">{appt.name}</td>
                <td className="px-4 py-3">{appt.slot_display}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{appt.reason}</td>
                <td className="px-4 py-3 font-mono text-xs">{appt.phone}</td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {formatCreatedAt(appt.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-[var(--border)] px-4 py-3">
        <p className="text-xs text-[var(--muted)]">
          {appointments.length} appointment{appointments.length === 1 ? "" : "s"}
        </p>
        <button
          type="button"
          onClick={load}
          className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs"
        >
          Refresh
        </button>
      </div>
    </section>
  );
}

function formatCreatedAt(value: string): string {
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
