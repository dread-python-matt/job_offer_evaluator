import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AiMatchResult,
  CurrentModelConfig,
  MatchedOffer,
  MatchSortBy,
  ModelUsageSummaryItem,
  OfferFilters,
  OffersPage,
  SortOrder,
  UserProfile,
} from '../models/profile.model';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  getProfile(): Observable<UserProfile> {
    return this.http.get<UserProfile>(`${this.baseUrl}/profile`);
  }

  saveProfile(profile: UserProfile): Observable<UserProfile> {
    return this.http.post<UserProfile>(`${this.baseUrl}/profile`, profile);
  }

  matchOffers(
    candidate: UserProfile,
    offersLimit: number | null,
    minScore: number,
    location: string | null,
    minSalary: number | null,
    level: string[],
    tech: string[],
    sortBy: MatchSortBy = 'score',
    sortOrder: SortOrder = 'desc',
  ): Observable<MatchedOffer[]> {
    return this.http.post<MatchedOffer[]>(`${this.baseUrl}/offers/match`, {
      candidate,
      offers_limit: offersLimit,
      min_score: minScore,
      location,
      min_salary: minSalary,
      level,
      tech,
      sort_by: sortBy,
      sort_order: sortOrder,
    });
  }

  matchOffersWithAi(
    candidate: UserProfile,
    offersLimit: number | null,
    minScore: number,
    location: string | null,
    minSalary: number | null,
    level: string[],
    tech: string[],
    sortBy: MatchSortBy = 'score',
    sortOrder: SortOrder = 'desc',
    offersToScore: number = 20,
    aiMinScore: number = 0,
  ): Observable<AiMatchResult> {
    return this.http.post<AiMatchResult>(`${this.baseUrl}/offers/match/ai`, {
      candidate,
      offers_limit: offersLimit,
      min_score: minScore,
      location,
      min_salary: minSalary,
      level,
      tech,
      sort_by: sortBy,
      sort_order: sortOrder,
      offers_to_score: offersToScore,
      ai_min_score: aiMinScore,
    });
  }

  getOffersCount(): Observable<number> {
    return this.http
      .get<{ total: number }>(`${this.baseUrl}/offers/count`)
      .pipe(map((response) => response.total));
  }

  getCurrentModel(): Observable<CurrentModelConfig> {
    return this.http.get<CurrentModelConfig>(`${this.baseUrl}/config/model`);
  }

  getUsageSummary(): Observable<ModelUsageSummaryItem[]> {
    return this.http.get<ModelUsageSummaryItem[]>(`${this.baseUrl}/usage/summary`);
  }

  getOffers(limit: number, offset: number, filters: OfferFilters): Observable<OffersPage> {
    const params: Record<string, string | number> = { limit, offset };
    if (filters.location) params['location'] = filters.location;
    if (filters.minSalary != null) params['min_salary'] = filters.minSalary;
    if (filters.tech) params['tech'] = filters.tech;
    if (filters.search) params['search'] = filters.search;
    if (filters.level) params['level'] = filters.level;
    if (filters.sortBy) {
      params['sort_by'] = filters.sortBy;
      params['sort_order'] = filters.sortOrder;
    }

    return this.http.get<OffersPage>(`${this.baseUrl}/offers`, { params });
  }
}
