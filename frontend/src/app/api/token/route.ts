import { NextRequest, NextResponse } from "next/server";
import { AccessToken, AgentDispatchClient } from "livekit-server-sdk";

const LIVEKIT_URL = process.env.LIVEKIT_URL!;
const API_KEY = process.env.LIVEKIT_API_KEY!;
const API_SECRET = process.env.LIVEKIT_API_SECRET!;
const AGENT_NAME = process.env.AGENT_NAME ?? "swades-agent";

function getHttpUrl(wsUrl: string): string {
  return wsUrl.replace("wss://", "https://").replace("ws://", "http://");
}

export async function POST(req: NextRequest) {
  if (!LIVEKIT_URL || !API_KEY || !API_SECRET) {
    return NextResponse.json(
      { error: "LiveKit credentials not configured in .env.local" },
      { status: 500 },
    );
  }

  const body = await req.json();
  const role = (body.role as string) ?? "caller";
  const roomName =
    (body.roomName as string) ?? `call-${Date.now().toString(36)}`;
  const identity = `${role}-${Math.random().toString(36).slice(2, 9)}`;

  const canPublish = role === "caller" || role === "watcher";

  const token = new AccessToken(API_KEY, API_SECRET, {
    identity,
    metadata: JSON.stringify({ role }),
  });

  token.addGrant({
    roomJoin: true,
    room: roomName,
    canPublish,
    canSubscribe: true,
    canPublishData: true,
  });

  let dispatchError: string | null = null;

  // Dispatch agent when caller starts a web call
  if (role === "caller") {
    try {
      const dispatch = new AgentDispatchClient(
        getHttpUrl(LIVEKIT_URL),
        API_KEY,
        API_SECRET,
      );
      await dispatch.createDispatch(roomName, AGENT_NAME);
    } catch (err) {
      dispatchError =
        err instanceof Error ? err.message : "Failed to dispatch agent";
      console.error("Agent dispatch failed:", err);
    }
  }

  return NextResponse.json({
    token: await token.toJwt(),
    url: LIVEKIT_URL,
    roomName,
    identity,
    agentName: AGENT_NAME,
    dispatchError,
  });
}

export async function GET() {
  return NextResponse.json({
    inboundPhone: process.env.NEXT_PUBLIC_INBOUND_PHONE_NUMBER ?? null,
    livekitConfigured: Boolean(LIVEKIT_URL && API_KEY && API_SECRET),
  });
}
