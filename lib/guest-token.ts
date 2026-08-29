import crypto from 'crypto';

const GUEST_SECRET = process.env.GUEST_TOKEN_SECRET || "overbranch-guest-super-secret-key-replace-2026";
const SESSION_LIFETIME_SECONDS = 86400; // 24 hours

export function verifyGuestToken(token?: string | null): { sessionId: string; timestamp: number } | null {
  if (!token) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;

  const [sessionId, tsStr, signature] = parts;
  const ts = parseInt(tsStr, 10);
  if (isNaN(ts)) return null;

  const now = Math.floor(Date.now() / 1000);
  if (now - ts > SESSION_LIFETIME_SECONDS + 300 || ts > now + 300) {
    return null;
  }

  const expectedPayload = `${sessionId}.${ts}`;
  const expectedSig = crypto.createHmac('sha256', GUEST_SECRET).update(expectedPayload).digest('hex');

  try {
    const sigBuf = Buffer.from(signature, 'hex');
    const expBuf = Buffer.from(expectedSig, 'hex');
    if (sigBuf.length !== expBuf.length || !crypto.timingSafeEqual(sigBuf, expBuf)) {
      return null;
    }
  } catch {
    return null;
  }

  return { sessionId, timestamp: ts };
}
