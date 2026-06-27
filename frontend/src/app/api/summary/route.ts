import { execFile } from "child_process";
import { existsSync } from "fs";
import { NextRequest, NextResponse } from "next/server";
import path from "path";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export type CallSummaryRecord = {
  room_name: string;
  summary: string;
  created_at: string;
};

function resolvePython(): { python: string; cwd: string } {
  const backendDir = path.join(process.cwd(), "..", "backend");
  const venvPython = path.join(backendDir, ".venv", "bin", "python");
  const python = existsSync(venvPython) ? venvPython : "python3";
  return { python, cwd: backendDir };
}

export async function GET(req: NextRequest) {
  const roomName = req.nextUrl.searchParams.get("room")?.trim();
  if (!roomName) {
    return NextResponse.json({ error: "room query parameter is required" }, { status: 400 });
  }

  const script = path.join(
    process.cwd(),
    "..",
    "backend",
    "scripts",
    "get_call_summary.py",
  );

  if (!existsSync(script)) {
    return NextResponse.json({ error: "Summary script not found" }, { status: 500 });
  }

  try {
    const { python, cwd } = resolvePython();
    const { stdout } = await execFileAsync(python, [script, roomName], { cwd });
    const summary = JSON.parse(stdout) as CallSummaryRecord | null;
    return NextResponse.json({ summary });
  } catch (err) {
    console.error("Failed to load call summary:", err);
    return NextResponse.json({ error: "Failed to load call summary" }, { status: 500 });
  }
}
