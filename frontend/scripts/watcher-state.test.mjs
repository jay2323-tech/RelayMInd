import fs from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/ui/watcherState.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { openAlerts, outdatedTargets } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));
const alert = { id: 'alert-1', kind: 'approved_plan_stale', reason: 'Decision changed', target_id: 'handoff-1', run_id: 'run-1', session_id: 'session-1', basis: 'snapshot-1', status: 'open', resolved_at: null, created_at: 1, acknowledged_at: null };
test('acknowledgement dismisses notification without clearing target staleness', () => {
  assert.equal(openAlerts([alert]).length, 1);
  const acknowledged = { ...alert, acknowledged_at: 2, status: 'acknowledged' };
  assert.equal(openAlerts([acknowledged]).length, 0);
  assert.equal(outdatedTargets([acknowledged]).has('handoff-1'), true);
});
test('old targets do not mark a new handoff or another target outdated', () => {
  const targets = outdatedTargets([alert, { ...alert, id: 'alert-2' }]);
  assert.equal(targets.size, 1);
  assert.equal(targets.has('handoff-2'), false);
  assert.equal(targets.has('another-project-handoff'), false);
});

test('resolved conditions clear warnings even when the notification was never dismissed', () => {
  const resolved = { ...alert, status: 'resolved', resolved_at: 3 };
  assert.equal(openAlerts([resolved]).length, 0);
  assert.equal(outdatedTargets([resolved]).size, 0);
});
test('a later change keeps the exact handoff stale when the earlier alert resolves', () => {
  const resolved = { ...alert, status: 'resolved', resolved_at: 3 };
  const replacement = { ...alert, id: 'alert-2', basis: 'snapshot-2' };
  assert.equal(openAlerts([resolved, replacement]).length, 1);
  assert.deepEqual([...outdatedTargets([resolved, replacement])], ['handoff-1']);
});
test('action IDs and shared run IDs cannot mark a plan revision outdated', () => {
  const action = { ...alert, kind: 'action_stale', target_id: 'action-1' };
  assert.equal(outdatedTargets([action]).size, 0);
  assert.equal(outdatedTargets([alert]).has('run-1'), false);
});
