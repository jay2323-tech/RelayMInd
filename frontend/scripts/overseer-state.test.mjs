import fs from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';
const source = fs.readFileSync(new URL('../src/ui/overseerState.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { checkedSummary } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));
const message = { id: 'run-completed-summary', role: 'assistant' };
const run = { id: 'run', status: 'completed', overseer: { ok: true, checks_run: 10, failures: [], rewritten: false } };
test('passing and successfully rebuilt verdicts bind to the saved summary', () => {
  assert.equal(checkedSummary(run, message), true);
  assert.equal(checkedSummary({ ...run, overseer: { ...run.overseer, rewritten: true } }, message), true);
});
test('missing, failing, empty and contradictory verdicts have no success badge', () => {
  for (const candidate of [undefined, { ...run, overseer: null },
    { ...run, overseer: { ...run.overseer, ok: false } },
    { ...run, overseer: { ...run.overseer, checks_run: 0 } },
    { ...run, overseer: { ...run.overseer, failures: [{ check: 'scope', detail: 'failed' }] } }])
    assert.equal(checkedSummary(candidate, message), false);
});
test('never transfer a badge to another run, a prior state, or the user', () => {
  for (const candidate of [{ ...message, role: 'user' }, { ...message, id: 'run-paused-summary' }, { ...message, id: 'other-completed-summary' }])
    assert.equal(checkedSummary(run, candidate), false);
  assert.equal(checkedSummary({ ...run, status: 'blocked' }, { ...message, id: 'run-blocked-summary' }), false);
});
