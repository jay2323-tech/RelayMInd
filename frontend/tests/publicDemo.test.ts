import { test } from 'node:test';
import assert from 'node:assert/strict';
import { publicDemoInfo } from '../src/ui/publicDemo.ts';
const enabled = { public_demo: true, password: 'fixture-only', accounts: [{ username: 'fixture-user', label: 'Test workspace' }] };
test('only explicit public demo opt-in reveals credentials', () => {
 assert.deepEqual(publicDemoInfo(enabled), { password: enabled.password, accounts: enabled.accounts });
 for (const public_demo of [false, undefined, 'true', 1]) assert.equal(publicDemoInfo({...enabled, public_demo}), null);
});
test('malformed or missing access metadata keeps manual login', () => {
 for (const value of [null, {}, {...enabled, password: ''}, {...enabled, accounts: []}, {...enabled, accounts: [{username: 12}]}])
  assert.equal(publicDemoInfo(value), null);
});
