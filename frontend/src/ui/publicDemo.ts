export interface PublicDemo {
  password: string; accounts: { username: string; label: string }[];
}
/** Never infer public access from credentials alone; the server must opt in. */
export function publicDemoInfo(value: unknown): PublicDemo | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (data.public_demo !== true || typeof data.password !== 'string' || !data.password
      || !Array.isArray(data.accounts) || !data.accounts.length) return null;
  if (!data.accounts.every(account => account && typeof account === 'object'
      && typeof account.username === 'string' && account.username.length > 0
      && typeof account.label === 'string')) return null;
  return { password: data.password, accounts: data.accounts };
}
