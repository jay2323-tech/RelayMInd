import { test } from 'node:test';
import assert from 'node:assert/strict';
import { activityFeedback } from '../src/ui/activityState.ts';
const view = (status: string, agent: string, summary: string) => ({ job: { state: 'running' }, run: { status, events: [{ agent, summary }] } }) as any;
test('queue has no invented plan stage', () => {
  assert.equal(activityFeedback(null).state, 'connecting');
  assert.ok(!activityFeedback(null).label.includes('plan'));
});
test('only reported review state describes independent review', () => {
  assert.equal(activityFeedback(view('awaiting_review', 'planner', 'Saved handoff x-r1')).state, 'solving');
  assert.equal(activityFeedback(view('planning', 'system', 'Assistant routed this message: help')).state, 'shaping');
});
test('tool read and planner output get distinct feedback', () => {
  assert.equal(activityFeedback(view('planning', 'planner', 'Read fetch_evidence')).state, 'searching');
  assert.equal(activityFeedback(view('planning', 'planner', 'Retrieved approved decisions')).state, 'composing');
});
test('unknown activity remains generic instead of claiming checks passed', () => {
  assert.equal(activityFeedback(view('planning', 'system', 'unknown event')).state, 'working');
});
