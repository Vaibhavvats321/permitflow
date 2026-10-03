"use client";

import { useEffect, useState } from "react";

/**
 * Return `value` once it has stopped changing for `delayMs`.
 *
 * A search box that fires a request per keystroke asks the API to compute
 * answers nobody waits for, and the responses race each other back to the
 * screen. Pausing until typing pauses keeps the input immediate while the
 * network settles: the controlled input still shows every character as it is
 * typed, and only the debounced copy reaches the fetch.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
