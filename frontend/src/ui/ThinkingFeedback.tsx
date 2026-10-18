import { useEffect, useState, type ComponentProps } from 'react';
import { ThinkingOrb } from 'thinking-orbs';
import type { RunView } from '../types';
import { activityFeedback } from './activityState';

/** Static orb for reduced motion; suspend the animation in background tabs. */
export function StatusOrb({ state = 'working', size = 20 }: { state?: ComponentProps<typeof ThinkingOrb>['state']; size?: 20 | 42 | 64 }) {
  const [paused, setPaused] = useState(() => document.hidden || window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setPaused(document.hidden || media.matches);
    update(); media.addEventListener('change', update); document.addEventListener('visibilitychange', update);
    return () => { media.removeEventListener('change', update); document.removeEventListener('visibilitychange', update); };
  }, []);
  // Keep the library's tuned 64px canvas for custom 42px display sizing.
  // Downsampling preserves its animation clock and high-DPI rendering.
  return <span className="status-orb" aria-hidden="true"><ThinkingOrb state={state} size={size === 42 ? 64 : size}
    style={size === 42 ? { width: 42, height: 42 } : undefined} theme="dark" paused={paused} /></span>;
}

export function ThinkingFeedback({ view }: { view: RunView | null }) {
  const feedback = activityFeedback(view);
  return <div className="thinking-feedback" role="status" aria-live="polite" aria-atomic="true">
    <StatusOrb state={feedback.state} size={42} />
    <div><span className="thinking-feedback__name">RelayMind</span><strong>{feedback.label}</strong><p>{feedback.detail}</p></div>
  </div>;
}
