import { AbstractControl, ValidationErrors } from '@angular/forms';

// Mirrors the backend policy (app/domain/password_policy.py + the auth request schemas); the
// server enforces it regardless, this just gives the user immediate feedback.
export const MIN_PASSWORD_LENGTH = 8;

export const PASSWORD_REQUIREMENTS_HINT =
  'At least 8 characters, including a lowercase letter, an uppercase letter, a number, and a special character.';

// Character-class check (length is handled by Validators.minLength). A "special character" is
// anything that isn't a letter, digit, or whitespace, matching the backend's definition.
export function passwordStrength(control: AbstractControl): ValidationErrors | null {
  const value: string = control.value ?? '';
  if (!value) {
    return null; // empty is the `required` validator's concern, not this one's
  }
  const satisfied =
    /[a-z]/.test(value) &&
    /[A-Z]/.test(value) &&
    /[0-9]/.test(value) &&
    /[^A-Za-z0-9\s]/.test(value);
  return satisfied ? null : { passwordStrength: true };
}
