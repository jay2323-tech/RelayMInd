import fs from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/ui/planMessage.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { planMessage, planNeedsRefresh } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));
const handoff = { id: 'run-1-r1', plan: { decision_ids: ['decision-1'] } };
const view = { run: { id: 'run-1', status: 'completed' }, handoffs: [handoff] };
const summary = { id: 'run-1-completed-summary', role: 'assistant', content: 'Saved narrative' };
test('only the exact persisted summary owns a plan, even after receipt and alert messages arrive', () => {
  assert.equal(planMessage(summary, { 'run-1': view })[0], 'run-1');
  for (const id of ['run-1-r1-plan-review-receipt', 'alert-1-notice', 'run-1-paused-summary', 'run-10-completed-summary']) {
    assert.equal(planMessage({ ...summary, id }, { 'run-1': view }), null);
  }
  assert.equal(planMessage({ ...summary, role: 'user' }, { 'run-1': view }), null);
});
test('unverified or unloaded plans leave the original saved reply intact', () => {
  assert.equal(planMessage(summary, {}), null);
  assert.equal(planMessage(summary, { 'run-1': { ...view, handoffs: [] } }), null);
  assert.equal(planMessage(summary, { 'run-1': { ...view, run: { ...view.run, overseer: { ok: false } } } }), null);
});
test('resolved approval alert cannot make a historical plan current', () => {
  assert.equal(planNeedsRefresh(handoff, new Set(['decision-2']), {}), true);
  assert.equal(planNeedsRefresh(handoff, new Set(), {}), true); // loaded but conflicted/no current decision
  assert.equal(planNeedsRefresh(handoff, new Set(['decision-1']), {}), false);
  assert.equal(planNeedsRefresh(handoff, null, {}), false); // not loaded yet, no invented freshness verdict
});
test('manufacturing currency follows the exact hold snapshot', () => {
  const manufacturing = { ...handoff, manufacturing_versions: [{ evidence_id: 'QH-17', version_id: 'hold-v1' }] };
  assert.equal(planNeedsRefresh(manufacturing, new Set(['decision-1']), { 'QH-17': 'hold-v2' }), true);
  assert.equal(planNeedsRefresh(manufacturing, new Set(['decision-1']), { 'QH-17': 'hold-v1' }), false);
});
