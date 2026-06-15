/**
 * useActionPreview — drives the hover/focus action preview.
 *
 * On hover of a legal action we POST /games/{id}/preview to get the hypothetical
 * resulting state (the real game is untouched, no AI run), diff it against the
 * current state (preview.ts), and surface the deltas + a ghost board highlight.
 *
 * Mechanics encapsulated here:
 *   - debounce the network request (PREVIEW_DEBOUNCE_MS),
 *   - cancel any in-flight request via an AbortController,
 *   - cache diffs per action id, scoped to the current decision (decisionKey),
 *   - ignore stale responses once the decision context has moved on.
 */

import { useCallback, useMemo, useRef, useState } from "react";

import { previewAction } from "../api";
import { computePreviewDiff, type PreviewDiff } from "../preview";
import type {
  CatalogBuilding,
  Highlight,
  LegalAction,
  StateMsg,
} from "../types";

const PREVIEW_DEBOUNCE_MS = 120;

export interface ActionPreview {
  previewLabel: string | null;
  previewDiff: PreviewDiff | null;
  previewLoading: boolean;
  previewHighlight: Highlight;
  /** Request a preview for the hovered/focused action (null = clear). */
  onPreview: (action: LegalAction | null) => void;
  clearPreview: () => void;
}

export function useActionPreview(
  gameId: string,
  currentState: StateMsg | null,
  humanSeat: number,
  buildingInfo: (id: number) => CatalogBuilding | null,
): ActionPreview {
  const [previewLabel, setPreviewLabel] = useState<string | null>(null);
  const [previewDiff, setPreviewDiff] = useState<PreviewDiff | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewHighlight, setPreviewHighlight] = useState<Highlight>(null);

  const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewAbort = useRef<AbortController | null>(null);
  // Cache preview diffs per action id, scoped to the current decision state.
  const previewCache = useRef<Map<number, PreviewDiff>>(new Map());
  const previewStateKey = useRef<string>("");

  // A key identifying the current human-decision state, so the preview cache is
  // invalidated whenever the decision context changes.
  const decisionKey = useMemo(() => {
    if (!currentState) return "";
    const v = currentState.view;
    return `${v.phase}:${currentState.to_move}:${currentState.legal_actions
      .map((a) => a.id)
      .join(",")}`;
  }, [currentState]);

  const clearPreview = useCallback(() => {
    if (previewTimer.current !== null) {
      clearTimeout(previewTimer.current);
      previewTimer.current = null;
    }
    if (previewAbort.current !== null) {
      previewAbort.current.abort();
      previewAbort.current = null;
    }
    setPreviewLabel(null);
    setPreviewDiff(null);
    setPreviewLoading(false);
    setPreviewHighlight(null);
  }, []);

  const onPreview = useCallback(
    (action: LegalAction | null) => {
      // Reset the cache if the decision context changed.
      if (previewStateKey.current !== decisionKey) {
        previewStateKey.current = decisionKey;
        previewCache.current.clear();
      }
      if (action === null) {
        clearPreview();
        return;
      }
      if (!currentState) return;

      setPreviewLabel(action.label);

      // Serve from cache immediately if present.
      const cached = previewCache.current.get(action.id);
      if (cached) {
        if (previewTimer.current !== null) {
          clearTimeout(previewTimer.current);
          previewTimer.current = null;
        }
        setPreviewDiff(cached);
        setPreviewLoading(false);
        setPreviewHighlight(cached.highlight);
        return;
      }

      setPreviewDiff(null);
      setPreviewLoading(true);
      setPreviewHighlight(null);

      // Debounce the network request; cancel any in-flight one.
      if (previewTimer.current !== null) clearTimeout(previewTimer.current);
      previewTimer.current = setTimeout(() => {
        if (previewAbort.current !== null) previewAbort.current.abort();
        const ctrl = new AbortController();
        previewAbort.current = ctrl;
        const keyAtRequest = decisionKey;
        previewAction(gameId, action.id, ctrl.signal)
          .then((after) => {
            // Ignore stale responses (decision changed or hover moved on).
            if (keyAtRequest !== previewStateKey.current) return;
            const diff = computePreviewDiff(
              currentState,
              after,
              humanSeat,
              buildingInfo,
            );
            previewCache.current.set(action.id, diff);
            setPreviewDiff(diff);
            setPreviewLoading(false);
            setPreviewHighlight(diff.highlight);
          })
          .catch(() => {
            /* aborted or failed — leave the panel showing the label only */
            setPreviewLoading(false);
          });
      }, PREVIEW_DEBOUNCE_MS);
    },
    [clearPreview, currentState, decisionKey, gameId, humanSeat, buildingInfo],
  );

  return {
    previewLabel,
    previewDiff,
    previewLoading,
    previewHighlight,
    onPreview,
    clearPreview,
  };
}
