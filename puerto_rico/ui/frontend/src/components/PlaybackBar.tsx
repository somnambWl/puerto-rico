/**
 * PlaybackBar — persistent, discoverable controls for watching AI moves.
 *
 * Rendered AT ALL TIMES (not only while animating) so the human always knows
 * they can change the AI playback speed and that pause/step exist. The speed
 * selector is always shown. When AI frames are queued/animating (`active`), the
 * bar also shows "AI move X of N", the latest move label, and the
 * Pause/Step/Resume/Skip controls. Otherwise it shows a quiet idle hint.
 */

import type { PlaybackSpeed } from "../hooks/useGameState";

interface PlaybackBarProps {
  /** True while AI frames are queued / animating. */
  active: boolean;
  index: number;
  total: number;
  pendingCount: number;
  isPaused: boolean;
  speed: PlaybackSpeed;
  latestLabel: string | null;
  onPause: () => void;
  onResume: () => void;
  onStep: () => void;
  onSkip: () => void;
  onSpeed: (s: PlaybackSpeed) => void;
}

export function PlaybackBar({
  active,
  index,
  total,
  pendingCount,
  isPaused,
  speed,
  latestLabel,
  onPause,
  onResume,
  onStep,
  onSkip,
  onSpeed,
}: PlaybackBarProps) {
  return (
    <div className={"playback-bar" + (active ? " playback-active" : "")}>
      <div className="playback-info">
        {active ? (
          <>
            <span className="playback-counter">
              AI move {index} of {total}
            </span>
            {latestLabel && (
              <span className="playback-label">{latestLabel}</span>
            )}
          </>
        ) : (
          <span className="playback-label">AI playback controls</span>
        )}
      </div>
      <div className="playback-controls">
        {active &&
          (isPaused ? (
            <button
              className="pb-btn"
              onClick={onResume}
              disabled={pendingCount === 0}
            >
              ▶ Resume
            </button>
          ) : (
            <button className="pb-btn" onClick={onPause}>
              ⏸ Pause
            </button>
          ))}
        {active && (
          <button
            className="pb-btn"
            onClick={onStep}
            disabled={pendingCount === 0}
          >
            Step ▶
          </button>
        )}
        {active && (
          <button className="pb-btn" onClick={onSkip}>
            Skip ⏭
          </button>
        )}
        <label className="pb-speed-label">
          Speed
          <select
            className="pb-speed"
            value={speed}
            onChange={(e) => onSpeed(e.target.value as PlaybackSpeed)}
            title="Playback speed"
          >
            <option value="slow">Slow</option>
            <option value="normal">Normal</option>
            <option value="fast">Fast</option>
          </select>
        </label>
      </div>
      {active && (
        <span className="pb-hint" title="Keyboard shortcuts">
          Space: pause/step · →: step · S: skip
        </span>
      )}
    </div>
  );
}
