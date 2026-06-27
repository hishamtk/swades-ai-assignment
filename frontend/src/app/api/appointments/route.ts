import { execFile } from "child_process";
import { existsSync } from "fs";
import { NextResponse } from "next/server";
import path from "path";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export type AppointmentRecord = {
  id: number;
  name: string;
  reason: string;
  slot: string;
  slot_display: string;
  phone: string;
  created_at: string;
};

function resolveBackendDir(): string {
  const candidates = [
    path.join(process.cwd(), "..", "backend"),
    path.join(process.cwd(), "backend"),
    process.env.BACKEND_DIR,
  ].filter(Boolean) as string[];

  for (const dir of candidates) {
    if (existsSync(path.join(dir, "booking.py"))) {
      return dir;
    }
  }

  throw new Error(
    `Backend not found. Checked: ${candidates.join(", ")}`,
  );
}

function resolvePython(backendDir: string): string {
  const venvPython = path.join(backendDir, ".venv", "bin", "python");
  if (existsSync(venvPython)) return venvPython;
  return process.env.PYTHON_PATH || "python3";
}

export async function GET() {
  try {
    const backendDir = resolveBackendDir();
    const script = path.join(backendDir, "scripts", "list_appointments.py");
    const dbPath = path.join(backendDir, "data", "appointments.db");

    if (!existsSync(script)) {
      return NextResponse.json(
        { error: "Appointments script not found", backendDir },
        { status: 500 },
      );
    }

    const python = resolvePython(backendDir);
    const { stdout } = await execFileAsync(python, [script], {
      cwd: backendDir,
      env: { ...process.env, PYTHONPATH: backendDir },
    });

    const appointments = JSON.parse(stdout) as AppointmentRecord[];
    return NextResponse.json({
      appointments,
      db_exists: existsSync(dbPath),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to load appointments";
    console.error("Failed to load appointments:", err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
