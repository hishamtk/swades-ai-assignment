import { NextRequest, NextResponse } from "next/server";
import { RoomServiceClient } from "livekit-server-sdk";

const LIVEKIT_URL = process.env.LIVEKIT_URL!;
const API_KEY = process.env.LIVEKIT_API_KEY!;
const API_SECRET = process.env.LIVEKIT_API_SECRET!;

function getHttpUrl(wsUrl: string): string {
  return wsUrl.replace("wss://", "https://").replace("ws://", "http://");
}

export async function POST(req: NextRequest) {
  if (!LIVEKIT_URL || !API_KEY || !API_SECRET) {
    return NextResponse.json({ error: "LiveKit not configured" }, { status: 500 });
  }

  const { roomName, identity, muted } = await req.json();
  if (!roomName || !identity) {
    return NextResponse.json(
      { error: "roomName and identity required" },
      { status: 400 },
    );
  }

  const roomService = new RoomServiceClient(
    getHttpUrl(LIVEKIT_URL),
    API_KEY,
    API_SECRET,
  );

  const participants = await roomService.listParticipants(roomName);
  const agent = participants.find((p) => p.identity.startsWith("agent"));

  if (!agent) {
    return NextResponse.json({ error: "Agent not in room" }, { status: 404 });
  }

  for (const track of agent.tracks) {
    if (track.type === 0) {
      // AUDIO
      await roomService.mutePublishedTrack(
        roomName,
        agent.identity,
        track.sid,
        Boolean(muted),
      );
    }
  }

  return NextResponse.json({ ok: true, muted: Boolean(muted) });
}
