import { AiInsight, MatchedOffer } from '../models/profile.model';
import { formatSalaries } from './offer-format';

export const AI_RATE_MAX = 5;

export interface AiInsightRow {
  rate: number;
  rateMax: number;
  /** One entry per point on the scale; true for a filled star. */
  stars: boolean[];
  rateClass: 'rate-high' | 'rate-medium' | 'rate-low';
  pros: string[];
  cons: string[];
  reason: string;
}

export interface MatchedOfferRow {
  title: string;
  company: string;
  score: number;
  scoreLabel: string;
  scoreClass: 'score-high' | 'score-medium' | 'score-low';
  matchedSkills: string[];
  link: string;
  locations: string[];
  salaryLabel: string | null;
  levels: string[];
  aiInsight: AiInsightRow | null;
}

export function scoreClass(score: number): MatchedOfferRow['scoreClass'] {
  if (score >= 0.7) return 'score-high';
  if (score >= 0.4) return 'score-medium';
  return 'score-low';
}

function rateClass(rate: number): AiInsightRow['rateClass'] {
  if (rate >= 4) return 'rate-high';
  if (rate >= 3) return 'rate-medium';
  return 'rate-low';
}

export function toAiInsightRow(insight: AiInsight): AiInsightRow {
  return {
    rate: insight.rate,
    rateMax: AI_RATE_MAX,
    stars: Array.from({ length: AI_RATE_MAX }, (_, i) => i < insight.rate),
    rateClass: rateClass(insight.rate),
    pros: insight.pros,
    cons: insight.cons,
    reason: insight.rate_reason,
  };
}

export function toMatchedOfferRow(match: MatchedOffer): MatchedOfferRow {
  return {
    title: match.title,
    company: match.company,
    score: match.score,
    scoreLabel: `${Math.round(match.score * 100)}%`,
    scoreClass: scoreClass(match.score),
    matchedSkills: [...match.matched_skills].sort(),
    link: match.link,
    locations: match.locations,
    salaryLabel: formatSalaries(match.salaries),
    levels: match.levels,
    aiInsight: match.ai_insight ? toAiInsightRow(match.ai_insight) : null,
  };
}
