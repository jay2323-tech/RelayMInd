import type { HealthResponse } from '../types';

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', { signal });
  if (!response.ok) throw new Error(`Backend returned ${response.status}`);
  const data: unknown = await response.json();
  if (typeof data !== 'object' || data === null ||
      !('status' in data) || data.status !== 'ok' ||
      !('service' in data) || data.service !== 'relaymind' ||
      !('mode' in data) || data.mode !== 'scaffold') {
    throw new Error('Unexpected backend response');
  }
  return data as HealthResponse;
}
