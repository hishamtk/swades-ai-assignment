export async function fetchCallSummary(
  roomName: string,
): Promise<string | null> {
  const res = await fetch(`/api/summary?room=${encodeURIComponent(roomName)}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.summary?.summary ?? null;
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export async function pollCallSummary(
  roomName: string,
  {
    attempts = 40,
    intervalMs = 2000,
    initialDelayMs = 1500,
    signal,
  }: {
    attempts?: number;
    intervalMs?: number;
    initialDelayMs?: number;
    signal?: AbortSignal;
  } = {},
): Promise<string | null> {
  try {
    await delay(initialDelayMs, signal);
  } catch {
    return null;
  }

  for (let i = 0; i < attempts; i += 1) {
    if (signal?.aborted) return null;

    const summary = await fetchCallSummary(roomName);
    if (summary) return summary;

    if (i < attempts - 1) {
      try {
        await delay(intervalMs, signal);
      } catch {
        return null;
      }
    }
  }

  return null;
}
