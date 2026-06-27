export type CollectedCallerData = {
  name?: string | null;
  reason?: string | null;
  preferred_date?: string | null;
  preferred_time?: string | null;
  phone?: string | null;
  booking_status?: string | null;
};

export type MonitorEvent =
  | { type: "transcript"; role: string; text: string }
  | {
      type: "state";
      status: string;
      intent: string;
      action: string;
      takeover?: boolean;
    }
  | { type: "call_status"; status: string }
  | { type: "summary"; text: string }
  | { type: "collected_data"; data: CollectedCallerData };

export type ConnectionInfo = {
  token: string;
  url: string;
  roomName: string;
  identity: string;
  agentName?: string;
  dispatchError?: string | null;
};

export async function fetchToken(
  role: "caller" | "watcher",
  roomName?: string,
): Promise<ConnectionInfo> {
  const res = await fetch("/api/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, roomName }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error ?? "Failed to get token");
  }
  return res.json();
}

export function parseMonitorPayload(raw: Uint8Array): MonitorEvent | null {
  try {
    const text = new TextDecoder().decode(raw);
    return JSON.parse(text) as MonitorEvent;
  } catch {
    return null;
  }
}

export const STATUS_LABELS: Record<string, string> = {
  idle: "Idle",
  waiting_for_agent: "Waiting for agent",
  connected: "Connected",
  transferring: "Transferring",
  takeover: "Watcher Takeover",
  ended: "Ended",
};

export const ACTION_LABELS: Record<string, string> = {
  idle: "Idle",
  checking_availability: "Checking availability…",
  booking: "Booking appointment…",
  transferring: "Transferring to human…",
  takeover: "Watcher in control",
};

export const BOOKING_STATUS_LABELS: Record<string, string> = {
  collecting: "Collecting details",
  checking: "Checking availability",
  confirmed: "Booked",
};
