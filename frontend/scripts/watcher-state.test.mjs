import fs from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/ui/watcherState.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { openAlerts, outdatedTargets } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));
const alert = { id: 'alert-1', kind: 'stale_plan', reason: 'Decision changed', target_ids: ['handoff-1'], created_at: 1, acknowledged_at: null };
test('acknowledgement dismisses notification without clearing target staleness', () => {
  assert.equal(openAlerts([alert]).length, 1);
  const acknowledged = { ...alert, acknowledged_at: 2 };
  assert.equal(openAlerts([acknowledged]).length, 0);
  assert.equal(outdatedTargets([acknowledged]).has('handoff-1'), true);
});
test('old targets do not mark a new handoff or another target outdated', () => {
  const targets = outdatedTargets([alert, { ...alert, id: 'alert-2' }]);
  assert.equal(targets.size, 1);
  assert.equal(targets.has('handoff-2'), false);
  assert.equal(targets.has('another-project-handoff'), false);
});
