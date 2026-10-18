// Run: node --test frontend/tests/trackState.test.ts   (Node >= 23.6 strips types natively)
// Uses REAL persisted runs exported from FalkorDB (frontend/tests/fixtures/...), no invented sequences.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { deriveTrack, eventToBeat, newEvents } from '../src/ui/track/trackState.ts';

const evidence = JSON.parse(readFileSync(new URL('./fixtures/2026-10-17-live-runs-before-reset.json', import.meta.url), 'utf8'));
const runs = evidence.runs.map((r: { run: unknown }) => r.run) as any[];
const view = (run: any, job: string | null = 'done') => ({ run, job: job ? { state: job, error: null } : null, handoffs: [] });

test('idle and queued states need no run', () => {
  assert.equal(deriveTrack(null).phase, 'idle');
  const q = deriveTrack({ run: null, job: { state: 'queued', error: null }, handoffs: [] } as any);
  assert.equal(q.phase, 'queued'); assert.equal(q.waiting, true);
});

test('every recorded completed run ends at You with an accepted stamp', () => {
  const completed = runs.filter(r => r.status === 'completed');
  assert.ok(completed.length >= 1);
  for (const r of completed) {
    const s = deriveTrack(view(r) as any);
    assert.equal(s.phase, 'completed'); assert.equal(s.baton, 'you'); assert.equal(s.reviewStamp, 'accepted'); assert.equal(s.tone, 'ok');
  }
});

test('every recorded failed run stops at the station named by its error', () => {
  const failed = runs.filter(r => r.status === 'failed');
  assert.ok(failed.length >= 1);
  for (const r of failed) {
    const s = deriveTrack(view(r) as any);
    assert.equal(s.phase, 'failed'); assert.equal(s.tone, 'danger');
    assert.equal(s.failedAt, /^(independent_review|review)/.test(r.error ?? '') ? 'reviewer' : 'planner', r.error);
  }
});

test('recorded event summaries map to beats by prefix only', () => {
  const summaries = new Set(runs.flatMap(r => r.events.map((e: any) => e.summary)));
  for (const s of summaries) {
    const beat = eventToBeat(s as string);
    if ((s as string).startsWith('Read ')) assert.equal(beat.kind, 'tool');
    if ((s as string).startsWith('Saved handoff')) assert.equal(beat.kind, 'handoff');
    if (/^(Final review|Review) /.test(s as string)) assert.equal(beat.kind, 'review');
  }
  assert.deepEqual(eventToBeat('Something unexpected'), { kind: 'generic' });
});

test('paused and running review states', () => {
  const r = { ...runs.find(x => x.handoff_ids.length), status: 'paused', result: null, error: null };
  const p = deriveTrack(view(r) as any);
  assert.equal(p.phase, 'paused'); assert.equal(p.baton, 'handoff'); assert.equal(p.tone, 'warn');
  const rv = deriveTrack(view({ ...r, status: 'awaiting_review' }, 'running') as any);
  assert.equal(rv.active, 'reviewer'); assert.equal(rv.waiting, true);
});

test('newEvents returns only unseen events in order', () => {
  const r = runs.find(x => x.events.length >= 3);
  assert.deepEqual(newEvents(r.events, 1).map((e: any) => e.seq), r.events.slice(1).map((e: any) => e.seq));
  assert.equal(newEvents(r.events, 999).length, 0);
});
