export const COOKIE_PREFERENCES_KEY = "overbranch_cookie_consent";
export const COOKIE_PREFERENCES_CHANGED = "cookie_consent_updated";
export const OPEN_COOKIE_SETTINGS = "overbranch_open_cookie_settings";

type CookiePreferences = { analytics: boolean };
let temporaryPreferences: CookiePreferences | null = null;

export function readCookiePreferences(): CookiePreferences | null {
  if (temporaryPreferences) return temporaryPreferences;
  try {
    const stored = localStorage.getItem(COOKIE_PREFERENCES_KEY);
    if (!stored) return null;
    const choice = JSON.parse(stored);
    if (typeof choice?.analytics === "boolean") return { analytics: choice.analytics };
    if (choice?.status === "accepted" || choice?.status === "essential") {
      return { analytics: choice.status === "accepted" };
    }
  } catch {
    // An unavailable or malformed preference is treated as a first visit.
  }
  return null;
}

export function saveCookiePreferences(analytics: boolean) {
  temporaryPreferences = { analytics };
  try {
    localStorage.setItem(COOKIE_PREFERENCES_KEY, JSON.stringify({ analytics, timestamp: Date.now() }));
    temporaryPreferences = null;
  } catch {
    // The change still applies for the current page and client-side navigation.
  }
  window.dispatchEvent(new Event(COOKIE_PREFERENCES_CHANGED));
}
