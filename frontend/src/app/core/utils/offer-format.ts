import { Salary } from '../models/profile.model';

function formatNetAmount(salary: Salary): string | null {
  if (salary.net_min != null && salary.net_max != null) {
    return `${Math.round(salary.net_min)} - ${Math.round(salary.net_max)}`;
  }
  if (salary.net_monthly != null) return `${Math.round(salary.net_monthly)}`;
  return null;
}

function formatGrossAmount(salary: Salary): string | null {
  if (salary.min != null && salary.max != null) return `${salary.min} - ${salary.max}`;
  if (salary.min != null) return `${salary.min}`;
  if (salary.max != null) return `${salary.max}`;
  return null;
}

export function formatSalary(salary: Salary): string | null {
  // Prefer the standardized NET (the comparison basis), annotated as netto. Fall back
  // to the advertised gross (brutto) so offers without a normalized net still show one.
  const net = formatNetAmount(salary);
  if (net != null) return `${salary.contract_type}: ${net} PLN/mo netto (est.)`;

  const gross = formatGrossAmount(salary);
  if (gross != null) {
    return `${salary.contract_type}: ${gross} ${salary.currency}/${salary.period} brutto`;
  }
  return null;
}

export function formatSalaries(salaries: Salary[]): string | null {
  const formatted = salaries.map(formatSalary).filter((value): value is string => value != null);
  return formatted.length ? formatted.join('; ') : null;
}
