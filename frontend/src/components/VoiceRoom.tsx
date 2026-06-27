"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Room,
  RoomEvent,
  Track,
  ConnectionState,
  ParticipantKind,
} from "livekit-client";
import {
  fetchToken,
  parseMonitorPayload,
  type MonitorEvent,
} from "@/lib/livekit";
import { pollCallSummary } from "@/lib/summary";
import {
  AgentStatePanel,
  CallControls,
  CollectedDataPanel,
  PostCallSummary,
  TranscriptPanel,
} from "@/components/MonitorPanels";

type Props = {
  mode: "caller" | "watcher";
  initialRoom?: string;
};

export function VoiceRoom({ mode, initialRoom }: Props) {
  const roomRef = useRef<Room | null>(null);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [roomName, setRoomName] = useState(initialRoom ?? "");
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [callStatus, setCallStatus] = useState("idle");
  const [takeoverActive, setTakeoverActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentIdentity, setAgentIdentity] = useState<string | null>(null);
  const [agentJoined, setAgentJoined] = useState(false);
  const [summaryText, setSummaryText] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const pollAbortRef = useRef<AbortController | null>(null);
  const pollingRoomRef = useRef<string | null>(null);

  const isAgentParticipant = useCallback(
    (identity: string, kind?: ParticipantKind) => {
      if (kind === ParticipantKind.AGENT) return true;
      return identity.startsWith("agent") || identity.includes("agent");
    },
    [],
  );

  const pushEvent = useCallback((event: MonitorEvent) => {
    setEvents((prev) => [...prev, event]);
    if (event.type === "call_status") {
      setCallStatus(event.status);
      if (event.status === "ended" && roomName) {
        void loadSummaryRef.current?.(roomName);
      }
    }
    if (event.type === "state" && event.takeover !== undefined) {
      setTakeoverActive(event.takeover);
    }
    if (event.type === "summary") {
      setSummaryText(event.text);
      setSummaryLoading(false);
      pollingRoomRef.current = null;
    }
  }, [roomName]);

  const loadSummaryRef = useRef<(room: string) => Promise<void>>();

  const loadSummary = useCallback(async (activeRoom: string) => {
    if (!activeRoom) return;
    if (pollingRoomRef.current === activeRoom) return;

    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;
    pollingRoomRef.current = activeRoom;

    setSummaryLoading(true);
    const summary = await pollCallSummary(activeRoom, {
      signal: controller.signal,
    });
    if (controller.signal.aborted) return;

    if (summary) setSummaryText(summary);
    setSummaryLoading(false);
    pollingRoomRef.current = null;
  }, []);

  loadSummaryRef.current = loadSummary;

  const resetSession = useCallback(() => {
    pollAbortRef.current?.abort();
    pollingRoomRef.current = null;
    setEvents([]);
    setSummaryText(null);
    setSummaryLoading(false);
    setCallStatus("idle");
    setTakeoverActive(false);
    setAgentJoined(false);
    setAgentIdentity(null);
    setError(null);
  }, []);

  const enableMicrophone = useCallback(async (room: Room) => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      throw new Error(
        "Microphone is unavailable. Use HTTPS or localhost and allow mic access in your browser.",
      );
    }
    await room.localParticipant.setMicrophoneEnabled(true);
  }, []);

  const disableMicrophone = useCallback(async (room: Room) => {
    await room.localParticipant.setMicrophoneEnabled(false);
  }, []);

  const connect = useCallback(async () => {
    setConnecting(true);
    setError(null);
    resetSession();
    try {
      const info = await fetchToken(mode, roomName || undefined);
      setRoomName(info.roomName);

      if (info.dispatchError) {
        setError(
          `Agent dispatch failed: ${info.dispatchError}. Is the backend running (python agent.py dev)?`,
        );
      }

      const room = new Room();
      roomRef.current = room;

      room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
        if (topic !== "monitor") return;
        const event = parseMonitorPayload(payload);
        if (event) pushEvent(event);
      });

      room.on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
        setConnected(state === ConnectionState.Connected);
      });

      room.on(RoomEvent.ParticipantConnected, (participant) => {
        if (isAgentParticipant(participant.identity, participant.kind)) {
          setAgentIdentity(participant.identity);
          setAgentJoined(true);
          setCallStatus("connected");
        }
      });

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach();
          el.id = `audio-${track.sid}`;
          document.body.appendChild(el);
        }
      });

      await room.connect(info.url, info.token);
      // Watchers listen only until takeover — mic needs a user gesture (Take Over click)
      await room.localParticipant.setMicrophoneEnabled(mode === "caller");

      let foundAgent = false;
      for (const participant of room.remoteParticipants.values()) {
        if (isAgentParticipant(participant.identity, participant.kind)) {
          setAgentIdentity(participant.identity);
          setAgentJoined(true);
          foundAgent = true;
          setCallStatus("connected");
          break;
        }
      }

      if (mode === "caller" && !foundAgent) {
        setCallStatus("waiting_for_agent");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setConnecting(false);
    }
  }, [mode, roomName, pushEvent, resetSession]);

  const disconnect = useCallback(async () => {
    const activeRoom = roomName;
    roomRef.current?.disconnect();
    roomRef.current = null;
    setConnected(false);
    setTakeoverActive(false);
    setAgentJoined(false);
    setCallStatus("ended");
    document.querySelectorAll("audio").forEach((el) => el.remove());
    void loadSummary(activeRoom);
  }, [roomName, loadSummary]);

  const sendTakeover = useCallback(
    async (action: "start" | "end") => {
      const room = roomRef.current;
      if (!room) return;

      setError(null);

      try {
        if (action === "start") {
          // Request mic while the button click is still a valid user gesture
          await enableMicrophone(room);
        }

        const payload = new TextEncoder().encode(
          JSON.stringify({ type: "takeover", action }),
        );
        await room.localParticipant.publishData(payload, {
          reliable: true,
          topic: "monitor",
        });

        if (action === "start") {
          setTakeoverActive(true);
          if (agentIdentity) {
            await fetch("/api/mute-agent", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                roomName,
                identity: agentIdentity,
                muted: true,
              }),
            });
          }
        } else {
          await disableMicrophone(room);
          setTakeoverActive(false);
          if (agentIdentity) {
            await fetch("/api/mute-agent", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                roomName,
                identity: agentIdentity,
                muted: false,
              }),
            });
          }
        }
      } catch (err) {
        await disableMicrophone(room).catch(() => undefined);
        setError(
          err instanceof Error
            ? err.message
            : "Takeover failed — check microphone permissions",
        );
        if (action === "start") setTakeoverActive(false);
      }
    },
    [roomName, agentIdentity, enableMicrophone, disableMicrophone],
  );

  useEffect(() => {
    return () => {
      pollAbortRef.current?.abort();
      roomRef.current?.disconnect();
    };
  }, []);

  const liveSummary = [...events]
    .reverse()
    .find((e): e is Extract<MonitorEvent, { type: "summary" }> => e.type === "summary")
    ?.text;
  const displaySummary = summaryText ?? liveSummary ?? null;
  const showSessionRecap =
    !connected &&
    (events.length > 0 || displaySummary || summaryLoading || callStatus === "ended");

  return (
    <div className="flex flex-col gap-4">
      {!connected && (
        <div className="flex flex-col gap-3 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
          {mode === "watcher" && (
            <label className="text-sm">
              Room name (from active call)
              <input
                className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2"
                value={roomName}
                onChange={(e) => setRoomName(e.target.value)}
                placeholder="call-abc123 or SIP room name"
              />
            </label>
          )}
          {mode === "watcher" && roomName && !showSessionRecap && (
            <button
              type="button"
              onClick={() => {
                setCallStatus("ended");
                void loadSummary(roomName);
              }}
              className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm"
            >
              Load summary for this room
            </button>
          )}
          <button
            type="button"
            onClick={connect}
            disabled={connecting}
            className="rounded-lg bg-[var(--accent)] px-4 py-3 font-semibold text-white disabled:opacity-50"
          >
            {connecting
              ? "Connecting…"
              : mode === "caller"
                ? "Start Call with Agent A"
                : "Join as Watcher"}
          </button>
          {error && <p className="text-sm text-red-400">{error}</p>}
        </div>
      )}

      {showSessionRecap && (
        <section className="flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">Call ended</h2>
              <p className="text-xs text-[var(--muted)]">
                Room: <code>{roomName}</code>
              </p>
            </div>
            <button
              type="button"
              onClick={resetSession}
              className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs"
            >
              Clear &amp; start new
            </button>
          </div>
          <CollectedDataPanel events={events} />
          <TranscriptPanel events={events} callStatus={callStatus} />
          <PostCallSummary text={displaySummary} loading={summaryLoading} />
          {!summaryLoading && !displaySummary && (
            <button
              type="button"
              onClick={() => loadSummary(roomName)}
              className="self-start rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs"
            >
              Retry summary
            </button>
          )}
        </section>
      )}

      {connected && (
        <>
          <p className="text-sm text-[var(--muted)]">
            Room: <code className="text-[var(--foreground)]">{roomName}</code>
            {mode === "caller" && !agentJoined && (
              <span className="ml-2 text-[var(--warning)]">
                · Waiting for Agent A — ensure backend is running
              </span>
            )}
            {mode === "caller" && agentJoined && (
              <span className="ml-2 text-[var(--success)]">· Agent connected</span>
            )}
            {mode === "watcher" && (
              <span className="ml-2 text-[var(--accent)]">· Monitoring live</span>
            )}
          </p>

          {mode === "watcher" && (
            <CallControls
              connected={connected}
              takeoverActive={takeoverActive}
              onTakeover={() => sendTakeover("start")}
              onRelease={() => sendTakeover("end")}
              onDisconnect={disconnect}
            />
          )}

          {error && connected && (
            <p className="text-sm text-red-400">{error}</p>
          )}

          {mode === "caller" && (
            <button
              type="button"
              onClick={disconnect}
              className="self-start rounded-lg border border-red-500/50 px-4 py-2 text-sm text-red-400"
            >
              End Call
            </button>
          )}

          <AgentStatePanel events={events} />
          <CollectedDataPanel events={events} />
          <TranscriptPanel events={events} callStatus={callStatus} />
          <PostCallSummary text={displaySummary} loading={summaryLoading} />
        </>
      )}
    </div>
  );
}
