"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Run an async API call with loading / error / data state and stale-response protection.
 *
 * `run(...args)` calls `fn(...args, { signal })`; a newer call aborts the previous one, so a slow earlier
 * response can never overwrite a newer one. Errors are stored (not thrown) so components can show retry UI.
 */
export function useAsync(fn) {
  const [state, setState] = useState({ status: "idle", data: null, error: null });
  const controllerRef = useRef(null);
  const fnRef = useRef(fn);
  const mounted = useRef(true);

  useEffect(() => {
    fnRef.current = fn;
  });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const run = useCallback(async (...args) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((prev) => ({ status: "loading", data: prev.data, error: null }));
    try {
      const data = await fnRef.current(...args, { signal: controller.signal });
      if (controller.signal.aborted || !mounted.current) return undefined;
      setState({ status: "success", data, error: null });
      return data;
    } catch (error) {
      if (controller.signal.aborted || !mounted.current) return undefined;
      setState({ status: "error", data: null, error });
      return undefined;
    }
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setState({ status: "idle", data: null, error: null });
  }, []);

  return {
    ...state,
    loading: state.status === "loading",
    run,
    reset,
  };
}
