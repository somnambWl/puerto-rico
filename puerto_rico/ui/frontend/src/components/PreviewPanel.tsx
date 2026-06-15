/**
 * PreviewPanel — shows the diff of a hovered action vs the current state.
 *
 * Fed by the action-preview flow in App: on hover of a legal-action button we
 * POST /games/{id}/preview and diff the result. This panel renders the
 * resulting deltas (doubloons / goods / VP / build / role / ...) so the player
 * can weigh the option before committing. Real state is never mutated.
 */

import type { PreviewDiff } from "../preview";

interface PreviewPanelProps {
  label: string | null;
  diff: PreviewDiff | null;
  loading: boolean;
}

export function PreviewPanel({ label, diff, loading }: PreviewPanelProps) {
  if (!label) return null;
  return (
    <div className="preview-panel">
      <div className="preview-head">
        <span className="preview-tag">Preview</span>
        <span className="preview-action-label">{label}</span>
      </div>
      {loading && !diff && <div className="muted">computing…</div>}
      {diff && (
        <div className="preview-lines">
          {diff.lines.map((l, i) => (
            <div key={i} className="preview-line">
              <span className="preview-line-label">{l.label}</span>
              <span className="preview-line-change">{l.change}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
