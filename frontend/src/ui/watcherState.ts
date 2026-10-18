import type { WatcherAlert } from '../types/workflow';

export function openAlerts(alerts: WatcherAlert[]): WatcherAlert[] {
  return alerts.filter(alert => alert.status === 'open');
}

/** Acknowledgement changes notification state, never the historical target's freshness. */
export function outdatedTargets(alerts: WatcherAlert[]): Set<string> {
  return new Set(alerts.filter(alert => alert.status !== 'resolved' && alert.kind !== 'action_stale').map(alert => alert.target_id));
}
