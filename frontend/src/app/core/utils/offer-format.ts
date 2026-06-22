import { Salary } from '../models/profile.model';

function formatAmount(salary: Salary): string | null {
  if (salary.min != null && salary.max != null) return `${salary.min} - ${salary.max}`;
  if (salary.min != null) return `${salary.min}`;
  if (salary.max != null) return `${salary.max}`;
  return null;
}

export function formatSalary(salary: Salary): string | null {
  const amount = formatAmount(salary);
  if (amount == null) return null;
  return `${salary.contract_type}: ${amount} ${salary.currency}/${salary.period}`;
}

export function formatSalaries(salaries: Salary[]): string | null {
  const formatted = salaries.map(formatSalary).filter((value): value is string => value != null);
  return formatted.length ? formatted.join('; ') : null;
}
