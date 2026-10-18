import { test } from 'node:test';
import assert from 'node:assert/strict';
import { memoryTitleSpans } from '../src/ui/memoryLinks.ts';
const ref = (title: string, session = 'owned-chat') => ({ chat_title: title, session_id: session }) as any;
test('links exact server titles with their authorized session IDs', () => {
  assert.deepEqual(memoryTitleSpans('In "Coldline follow-up" you said: call early.', [ref('Coldline follow-up')]),
    [{ start: 4, title: 'Coldline follow-up', sessionId: 'owned-chat' }]);
});
test('does not guess a session for duplicate titles or unknown names', () => {
  assert.deepEqual(memoryTitleSpans('Follow-up', [ref('Follow-up', 'a'), ref('Follow-up', 'b')]), []);
  assert.deepEqual(memoryTitleSpans('Unknown chat', [ref('Follow-up')]), []);
});
test('deduplicates same-chat sources and prefers longest title', () => {
  const found = memoryTitleSpans('Coldline follow-up and Coldline', [ref('Coldline'), ref('Coldline follow-up'), ref('Coldline')]);
  assert.deepEqual(found.map(x => x.title), ['Coldline follow-up', 'Coldline']);
});
test('handles punctuation literally and never matches inside a word', () => {
  assert.equal(memoryTitleSpans('In "A [B].*" today', [ref('A [B].*')]).length, 1);
  assert.deepEqual(memoryTitleSpans('uncharted', [ref('chat')]), []);
});
