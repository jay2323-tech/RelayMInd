import type { MemoryRef } from '../types/index';
/** Exact metadata titles only. Ambiguous names use the explicit source list instead. */
export function memoryTitleSpans(text: string, refs: MemoryRef[]) {
  const sessions = new Map<string, Set<string>>();
  for (const ref of refs) {
    if (!ref.chat_title.trim() || !ref.session_id) continue;
    const ids = sessions.get(ref.chat_title) ?? new Set<string>();
    ids.add(ref.session_id); sessions.set(ref.chat_title, ids);
  }
  const titles = [...sessions].filter(([, ids]) => ids.size === 1).sort(([a], [b]) => b.length - a.length);
  const spans: { start: number; title: string; sessionId: string }[] = [];
  for (let i = 0; i < text.length; i++) {
    const match = titles.find(([title]) => text.startsWith(title, i)
      && (i === 0 || !/[\p{L}\p{N}_]/u.test(text[i - 1]))
      && (i + title.length === text.length || !/[\p{L}\p{N}_]/u.test(text[i + title.length])));
    if (!match) continue;
    spans.push({ start: i, title: match[0], sessionId: [...match[1]][0] });
    i += match[0].length - 1;
  }
  return spans;
}
