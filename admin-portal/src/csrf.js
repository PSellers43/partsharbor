import { createHash, randomBytes } from "node:crypto";

const DELIMITER = "|";

function hashToken(sessionId, csrfToken, secret) {
  return createHash("sha256").update(`${sessionId}${csrfToken}${secret}`).digest("hex");
}

export function readCsrfCookie(request, cookieName) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === cookieName) return decodeURIComponent(rest.join("="));
  }
  return undefined;
}

export function generateCsrfToken(sessionId, secret) {
  const csrfToken = randomBytes(32).toString("hex");
  const csrfTokenHash = hashToken(sessionId, csrfToken, secret);
  return {
    csrfToken,
    cookieValue: `${csrfToken}${DELIMITER}${csrfTokenHash}`,
  };
}

/**
 * @param {boolean} overwrite When true, always mint a new token (after login session rotation).
 * @param {boolean} validateOnReuse When false, invalid cookie pair is replaced instead of rejected.
 */
export function resolveCsrfToken(request, sessionId, secret, cookieName, overwrite, validateOnReuse) {
  const existing = readCsrfCookie(request, cookieName);
  if (!overwrite && typeof existing === "string") {
    const [csrfToken, csrfTokenHash] = existing.split(DELIMITER);
    if (
      typeof csrfToken === "string" &&
      typeof csrfTokenHash === "string" &&
      csrfTokenHash === hashToken(sessionId, csrfToken, secret)
    ) {
      return { csrfToken, cookieValue: existing, valid: true };
    }
    if (validateOnReuse) {
      return { valid: false, error: "invalid_csrf" };
    }
  }
  const minted = generateCsrfToken(sessionId, secret);
  return { ...minted, valid: true };
}

export function validateCsrfSubmission(request, sessionId, secret, cookieName, bodyToken) {
  const existing = readCsrfCookie(request, cookieName);
  if (typeof existing !== "string" || typeof bodyToken !== "string") return false;
  const [csrfToken, csrfTokenHash] = existing.split(DELIMITER);
  if (csrfToken !== bodyToken) return false;
  return csrfTokenHash === hashToken(sessionId, csrfToken, secret);
}
