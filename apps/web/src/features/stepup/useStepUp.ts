import { useCallback, useEffect, useRef, useState } from "react";

import type { StepUpRequest } from "./StepUpDialog";

/** Returns [request, ask, dialogHandlers]. `ask` resolves with a step-up token or null if cancelled. */
export function useStepUp() {
  const [request, setRequest] = useState<StepUpRequest | null>(null);
  const resolver = useRef<((token: string | null) => void) | null>(null);
  useEffect(() => () => {
    resolver.current?.(null);
    resolver.current = null;
  }, []);
  const ask = useCallback((r: StepUpRequest) => {
    resolver.current?.(null);
    setRequest(r);
    return new Promise<string | null>((resolve) => {
      resolver.current = resolve;
    });
  }, []);
  const onConfirmed = (token: string) => {
    resolver.current?.(token);
    resolver.current = null;
    setRequest(null);
  };
  const onCancel = () => {
    resolver.current?.(null);
    resolver.current = null;
    setRequest(null);
  };
  return { request, ask, onConfirmed, onCancel };
}
