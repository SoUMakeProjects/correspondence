import { useEffect, useState } from "react";

// Requests never overlap. Changing the resource aborts its old request and timer.
export function useDeskData<T>(
  read: (signal: AbortSignal) => Promise<T>,
  interval = 1500,
  retain = false,
) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    if (!retain) setValue(null);
    setError("");
    async function poll() {
      try {
        const result = await read(controller.signal);
        if (!controller.signal.aborted) {
          setValue(result);
          setError("");
        }
      } catch (reason) {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to load records.",
          );
      }
      if (!controller.signal.aborted && interval)
        timer = setTimeout(() => void poll(), interval);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [read, interval, retain]);
  return { value, error };
}
