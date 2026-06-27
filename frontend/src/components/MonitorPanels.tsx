"use client";

import type { CollectedCallerData, MonitorEvent } from "@/lib/livekit";
import { ACTION_LABELS, BOOKING_STATUS_LABELS, STATUS_LABELS } from "@/lib/livekit";

type Props = {
  events: MonitorEvent[];
  callStatus: string;
};

export function TranscriptPanel({ events, callStatus }: Props) {
  const lines = events.filter((e) => e.type === "transcript");

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          Live Transcript
        </h2>
        <span className="rounded-full bg-[var(--border)] px-2 py-0.5 text-xs">
          {STATUS_LABELS[callStatus] ?? callStatus}
        </span>
      </div>
      <div className="flex max-h-80 flex-col gap-2 overflow-y-auto text-sm">
        {lines.length === 0 && (
          <p className="text-[var(--muted)]">Waiting for conversation…</p>
        )}
        {lines.map((line, i) => (
          <div key={i} className="rounded-lg bg-[var(--background)] px-3 py-2">
            <span
              className={
                line.role === "user"
                  ? "font-medium text-[var(--accent)]"
                  : "font-medium text-[var(--success)]"
              }
            >
              {line.role === "user" ? "Caller" : "Agent A"}
            </span>
            <p className="mt-1">{line.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function FieldRow({
  label,
  value,
  confirmed = false,
}: {
  label: string;
  value?: string | null;
  confirmed?: boolean;
}) {
  const filled = Boolean(value?.trim());

  return (
    <div className="rounded-lg bg-[var(--background)] px-3 py-2">
      <dt className="text-xs text-[var(--muted)]">{label}</dt>
      <dd
        className={`mt-0.5 text-sm font-medium ${
          filled
            ? confirmed
              ? "text-[var(--success)]"
              : "text-[var(--foreground)]"
            : "text-[var(--muted)]"
        }`}
      >
        {filled ? value : "—"}
      </dd>
    </div>
  );
}

export function CollectedDataPanel({ events }: { events: MonitorEvent[] }) {
  const latest = [...events]
    .reverse()
    .find((e): e is Extract<MonitorEvent, { type: "collected_data" }> =>
      e.type === "collected_data",
    );

  const data: CollectedCallerData = latest?.data ?? {};
  const hasAnyField = Boolean(
    data.name || data.reason || data.preferred_date || data.preferred_time || data.phone,
  );
  const bookingStatus = data.booking_status ?? null;
  const dateTime =
    [data.preferred_date, data.preferred_time].filter(Boolean).join(" at ") || null;

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          Collected Data
        </h2>
        {bookingStatus && (
          <span
            className={`rounded-full px-2 py-0.5 text-xs ${
              bookingStatus === "confirmed"
                ? "bg-[var(--success)]/20 text-[var(--success)]"
                : "bg-[var(--border)] text-[var(--foreground)]"
            }`}
          >
            {BOOKING_STATUS_LABELS[bookingStatus] ?? bookingStatus}
          </span>
        )}
      </div>
      {!hasAnyField && !bookingStatus ? (
        <p className="text-sm text-[var(--muted)]">
          Fields appear here as the agent confirms them with the caller.
        </p>
      ) : (
        <dl className="grid gap-2 sm:grid-cols-2">
          <FieldRow label="Name" value={data.name} confirmed={bookingStatus === "confirmed"} />
          <FieldRow label="Phone" value={data.phone} confirmed={bookingStatus === "confirmed"} />
          <FieldRow
            label="Reason for visit"
            value={data.reason}
            confirmed={bookingStatus === "confirmed"}
          />
          <FieldRow
            label="Preferred date & time"
            value={dateTime}
            confirmed={bookingStatus === "confirmed"}
          />
        </dl>
      )}
    </section>
  );
}

export function AgentStatePanel({ events }: { events: MonitorEvent[] }) {
  const latestState = [...events]
    .reverse()
    .find((e) => e.type === "state") as
    | Extract<MonitorEvent, { type: "state" }>
    | undefined;

  const status = latestState?.status ?? "—";
  const intent = latestState?.intent ?? "—";
  const action = latestState?.action ?? "idle";

  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
        Agent State
      </h2>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-[var(--muted)]">Status</dt>
          <dd className="font-medium capitalize">{status}</dd>
        </div>
        <div>
          <dt className="text-[var(--muted)]">Intent</dt>
          <dd className="font-medium capitalize">{intent}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-[var(--muted)]">Action</dt>
          <dd className="font-medium">{ACTION_LABELS[action] ?? action}</dd>
        </div>
      </dl>
    </section>
  );
}

export function PostCallSummary({
  text,
  loading = false,
}: {
  text?: string | null;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          Post-Call Summary
        </h2>
        <p className="text-sm text-[var(--muted)]">Generating summary…</p>
      </section>
    );
  }

  if (!text) return null;

  return (
    <section className="rounded-xl border border-[var(--success)]/40 bg-[var(--card)] p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--success)]">
        Post-Call Summary
      </h2>
      <p className="whitespace-pre-wrap text-sm">{text}</p>
    </section>
  );
}

export function CallControls({
  connected,
  takeoverActive,
  onTakeover,
  onRelease,
  onDisconnect,
}: {
  connected: boolean;
  takeoverActive: boolean;
  onTakeover: () => void;
  onRelease: () => void;
  onDisconnect: () => void;
}) {
  return (
    <section className="flex flex-wrap gap-2">
      {!takeoverActive ? (
        <button
          type="button"
          disabled={!connected}
          onClick={onTakeover}
          className="rounded-lg bg-[var(--warning)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-40"
        >
          Take Over
        </button>
      ) : (
        <button
          type="button"
          onClick={onRelease}
          className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white"
        >
          Release to Agent
        </button>
      )}
      <button
        type="button"
        onClick={onDisconnect}
        className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm"
      >
        Leave Room
      </button>
    </section>
  );
}
