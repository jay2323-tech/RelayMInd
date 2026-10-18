import type { WatcherAlert } from '../types/workflow';

export function openAlerts(alerts: WatcherAlert[]): WatcherAlert[] {
  return alerts.filter(alert => alert.acknowledged_at == null);
}

/** Acknowledgement changes notification state, never the historical target's freshness. */
export function outdatedTargets(alerts: WatcherAlert[]): Set<string> {
  return new Set(alerts.flatMap(alert => alert.target_ids));
}
