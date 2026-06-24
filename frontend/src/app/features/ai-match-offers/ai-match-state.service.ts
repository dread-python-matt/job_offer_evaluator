import { Injectable, signal } from '@angular/core';

import { ModelUsage } from '../../core/models/profile.model';
import { MatchedOfferRow } from '../../core/utils/offer-row';

export type AiMatchSortOption =
  | 'score'
  | 'score-recent'
  | 'salary_max-desc'
  | 'salary_max-asc'
  | 'salary_mid-desc'
  | 'salary_mid-asc'
  | 'salary_min-desc'
  | 'salary_min-asc'
  | 'recent-desc'
  | 'recent-asc';

export interface AiMatchFilters {
  offersLimit: number | null;
  offersToScore: number;
  minScore: number;
  aiMinScore: number;
  location: string | null;
  minSalary: number | null;
  level: string[];
  sort: AiMatchSortOption;
}

/**
 * Holds the last AI-matching result so it survives navigating away from the
 * Ai-match-offers route and back. The component is destroyed on navigation, but
 * this service is a root-scoped singleton, so its signals persist for the
 * lifetime of the app.
 */
@Injectable({ providedIn: 'root' })
export class AiMatchStateService {
  readonly results = signal<MatchedOfferRow[]>([]);
  readonly usage = signal<ModelUsage | null>(null);
  readonly searched = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly techFilter = signal<string[]>([]);
  readonly filters = signal<AiMatchFilters | null>(null);
}
