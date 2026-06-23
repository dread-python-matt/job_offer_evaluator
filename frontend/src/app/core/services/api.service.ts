import { HttpClient, HttpParams } from '@angular/common/http';
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

export interface MatchOffersOptions {
  candidate: UserProfile;
  offersLimit: number | null;
  minScore: number;
  location: string | null;
  minSalary: number | null;
  level: string[];
  tech: string[];
  sortBy?: MatchSortBy;
  sortOrder?: SortOrder;
}

export interface MatchOffersWithAiOptions extends MatchOffersOptions {
  offersToScore?: number;
  aiMinScore?: number;
}

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

  matchOffers(options: MatchOffersOptions): Observable<MatchedOffer[]> {
    const { candidate, offersLimit, minScore, location, minSalary, level, tech, sortBy = 'score', sortOrder = 'desc' } = options;
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

  matchOffersWithAi(options: MatchOffersWithAiOptions): Observable<AiMatchResult> {
    const {
      candidate,
      offersLimit,
      minScore,
      location,
      minSalary,
      level,
      tech,
      sortBy = 'score',
      sortOrder = 'desc',
      offersToScore = 20,
      aiMinScore = 0,
    } = options;
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
    let params = new HttpParams().set('limit', limit).set('offset', offset);

    if (filters.location) params = params.set('location', filters.location);
    if (filters.minSalary != null) params = params.set('min_salary', filters.minSalary);
    if (filters.tech?.length) {
      for (const t of filters.tech) {
        params = params.append('tech', t);
      }
    }
    if (filters.search) params = params.set('search', filters.search);
    if (filters.level) params = params.set('level', filters.level);
    params = params.set('sort_by', filters.sortBy).set('sort_order', filters.sortOrder);

    return this.http.get<OffersPage>(`${this.baseUrl}/offers`, { params });
  }
}
