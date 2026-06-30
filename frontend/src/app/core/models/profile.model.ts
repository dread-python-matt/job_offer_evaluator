export interface Skill {
  name: string;
  rating: number;
}

export interface Project {
  name: string;
  repository_link: string;
  summary: string;
  date_from: string;
  date_to: string;
  tech_stack: string[];
}

export interface Experience {
  title: string;
  company: string;
  description: string;
  date_from: string;
  date_to: string;
  tech_stack: string[];
}

export type B2BTaxForm = 'ryczalt_12' | 'ryczalt_8_5' | 'liniowy' | 'skala';
export type ZusScheme = 'duzy_zus' | 'preferential' | 'ulga_na_start';

export interface TaxSituation {
  under_26: boolean;
  is_student: boolean;
  applies_tax_credit: boolean;
  b2b_tax_form: B2BTaxForm;
  b2b_zus_scheme: ZusScheme;
}

export interface UserProfile {
  summary: string;
  skills: Skill[];
  projects: Project[];
  experience: Experience[];
  tax_situation?: TaxSituation;
}

export interface Salary {
  contract_type: string;
  min: number | null;
  max: number | null;
  // Standardized estimated NET monthly PLN. `net_monthly` is the midpoint.
  net_monthly: number | null;
  net_min: number | null;
  net_max: number | null;
  currency: string;
  period: string;
}

export type SortBy = 'recent' | 'salary_min' | 'salary_mid' | 'salary_max';
export type MatchSortBy =
  | 'score'
  | 'recent'
  | 'score_recent'
  | 'salary_min'
  | 'salary_mid'
  | 'salary_max';
export type SortOrder = 'asc' | 'desc';

export interface AiInsight {
  rate: number;
  pros: string[];
  cons: string[];
  rate_reason: string;
}

export interface MatchedOffer {
  link: string;
  title: string;
  company: string;
  score: number;
  matched_skills: string[];
  locations: string[];
  salaries: Salary[];
  expired: boolean;
  expires: string | null;
  levels: string[];
  published: string | null;
  ai_insight: AiInsight | null;
}

export interface Offer {
  link: string;
  title: string;
  company: string;
  locations: string[];
  salaries: Salary[];
  tech_stack: string[];
  tech_stack_nice_to_have: string[];
  expired: boolean;
  expires: string | null;
  levels: string[];
  published: string | null;
}

export interface OffersPage {
  offers: Offer[];
  total: number;
  limit: number;
  offset: number;
}

export interface OfferFilters {
  location: string | null;
  minSalary: number | null;
  tech: string[] | null;
  search: string | null;
  level: string[] | null;
  sortBy: SortBy;
  sortOrder: SortOrder;
}

export interface ModelUsage {
  input_tokens: number;
  output_tokens: number;
}

export interface CurrentModelConfig {
  model: string;
  company: string;
}

export interface DailyCost {
  cost_usd: number;
  limit_usd: number;
}

export interface Budget {
  limit_usd: number;
  used_usd: number | null;
  tracking_since: string;
}

export interface CompanyModels {
  name: string;
  models: string[];
}

export interface AvailableModels {
  companies: CompanyModels[];
  active: CurrentModelConfig;
}

export interface ModelLimits {
  rpm: number;
  tpm: number;
  rpd: number;
}

export interface ModelUsageSummaryItem {
  company: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  limits: ModelLimits | null;
}

export interface AiMatchResult {
  matches: MatchedOffer[];
  usage: ModelUsage | null;
}

export interface ApiProvider {
  provider: string;
  company: string;
}

export interface ApiKey {
  api_provider: string;
  key_hint: string;
  limit_usd: number;
  used_usd: number;
}

export interface OrgSpend {
  spend_usd: number;
  since: string;
}

export interface AdminKey {
  key_hint: string;
  created_at: string;
}
