// Mirrors the backend access rules in main.py: record-level routers (trainees,
// follow-ups, notifications, verifications, wages, identity, imports) are
// admin-only; aggregated /api/analytics/* and /api/insights/* allow analysts too.
export const ADMIN_ONLY = ['admin'];
export const ANALYTICS_ROLES = ['admin', 'analyst'];

export function hasRole(user, roles) {
  return roles.includes(user?.role?.toLowerCase());
}
