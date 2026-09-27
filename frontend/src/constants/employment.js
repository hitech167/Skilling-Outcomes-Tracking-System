// Retention statuses — must match ALLOWED_EMPLOYMENT_STATUSES in
// schemas/employment_status.py (POST /api/employment-status).
export const RETENTION_STATUSES = ['Active', 'On Leave', 'Left Job', 'Terminated', 'Unknown'];

// "Left" is the older status stored on employment records themselves
// (schemas/employment.py), shown until a status change is recorded.
export const RETENTION_STATUS_COLORS = {
  Active: 'green',
  'On Leave': 'blue',
  'Left Job': 'orange',
  Left: 'orange',
  Terminated: 'red',
  Unknown: 'default',
};
