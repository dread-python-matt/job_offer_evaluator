import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { MatchedOffer, UserProfile } from '../models/profile.model';

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
  ): Observable<MatchedOffer[]> {
    return this.http.post<MatchedOffer[]>(`${this.baseUrl}/offers/match`, {
      candidate,
      offers_limit: offersLimit,
      min_score: minScore,
    });
  }
}
