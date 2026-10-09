import { useCallback, useEffect, useState } from "react";

/** The current `#/route` (one of `routes`), kept in the URL so reloads and links keep the view. */
export function useHashRoute<T extends string>(routes: readonly T[], fallback: T): [T, (route: T) => void] {
  const read = useCallback((): T => {
    const hash = window.location.hash.replace(/^#\/?/, "");
    return (routes as readonly string[]).includes(hash) ? (hash as T) : fallback;
  }, [routes, fallback]);

  const [route, setRoute] = useState<T>(read);

  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, [read]);

  const navigate = useCallback((next: T) => {
    window.location.hash = `/${next}`;
  }, []);

  return [route, navigate];
}
