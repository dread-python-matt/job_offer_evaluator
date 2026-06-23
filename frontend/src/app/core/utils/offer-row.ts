import { MatchedOffer } from '../models/profile.model';
import { formatSalaries } from './offer-format';

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
}

export function scoreClass(score: number): MatchedOfferRow['scoreClass'] {
  if (score >= 0.7) return 'score-high';
  if (score >= 0.4) return 'score-medium';
  return 'score-low';
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
  };
}
