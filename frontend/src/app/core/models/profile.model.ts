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

export interface UserProfile {
  summary: string;
  skills: Skill[];
  projects: Project[];
  experience: Experience[];
}

export interface Salary {
  contract_type: string;
  min: number | null;
  max: number | null;
  net_monthly: number | null;
  currency: string;
  period: string;
}

export type SortBy = 'salary' | 'recent';
export type MatchSortBy = 'score' | 'salary' | 'recent' | 'score_recent';
export type SortOrder = 'asc' | 'desc';

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
  level: string | null;
  sortBy: SortBy | null;
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
