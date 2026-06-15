/**
 * PlaybackBar — controls for watching AI moves frame by frame.
 *
 * Visible whenever there are queued AI frames (isAnimating). Shows "AI move
 * X of N", the latest move label, a speed selector, and Pause/Step/Resume/Skip
 * buttons so the human can watch the AI at their own pace.
 */

import type { PlaybackSpeed } from "../hooks/useGameState";

interface PlaybackBarProps {
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
    <div className="playback-bar">
      <div className="playback-info">
        <span className="playback-counter">
          AI move {index} of {total}
        </span>
        {latestLabel && (
          <span className="playback-label">{latestLabel}</span>
        )}
      </div>
      <div className="playback-controls">
        {isPaused ? (
          <button className="pb-btn" onClick={onResume} disabled={pendingCount === 0}>
            ▶ Resume
          </button>
        ) : (
          <button className="pb-btn" onClick={onPause}>
            ⏸ Pause
          </button>
        )}
        <button className="pb-btn" onClick={onStep} disabled={pendingCount === 0}>
          Step ▶
        </button>
        <button className="pb-btn" onClick={onSkip}>
          Skip ⏭
        </button>
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
      </div>
    </div>
  );
}
