/**
 * authStorage — local single-user fork stub.
 *
 * Real auth was removed; backend `require_admin` is a no-op. Consumers
 * (HealthPage, PortfolioDashboard, CronController, api.ts) still call
 * `authStorage.getAccessToken()` to attach a `Bearer local` header, which
 * the backend ignores. Kept as a single object so call sites compile.
 */

const LOCAL_TOKEN = "local";

export const authStorage = {
  getAccessToken(): string | null {
    return LOCAL_TOKEN;
  },
};
