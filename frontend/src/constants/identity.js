// Common external ID types. The backend accepts any id_type (2-60 chars) and
// matches types case-insensitively, so these are suggestions, not a fixed list.
export const ID_TYPE_OPTIONS = [
  'Skill India Digital ID',
  'PMKVY Candidate ID',
  'DDU-GKY Candidate ID',
  'State Scheme Registration No',
].map((value) => ({ value }));

// Mirrors the backend rules in schemas/identity.py: Aadhaar numbers must never be stored.
export const idTypeRules = [
  { required: true, whitespace: true, message: 'Please enter the ID type' },
  { min: 2, max: 60, message: 'ID type must be 2–60 characters' },
  {
    validator: (_, value) =>
      value && /aadha?ar/i.test(value)
        ? Promise.reject(new Error('Aadhaar numbers must not be stored; use a programme or Skill India ID'))
        : Promise.resolve(),
  },
];

export const idValueRules = [
  { required: true, whitespace: true, message: 'Please enter the ID value' },
  { max: 100, message: 'ID value must be at most 100 characters' },
  {
    validator: (_, value) =>
      value && /^\d{12}$/.test(value.replace(/[\s-]/g, ''))
        ? Promise.reject(new Error('A 12-digit number looks like an Aadhaar number and cannot be stored'))
        : Promise.resolve(),
  },
];

export function filterIdType(input, option) {
  return option.value.toLowerCase().includes(input.toLowerCase());
}
