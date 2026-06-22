import { Routes } from '@angular/router';

import { AiMatchOffers } from './features/ai-match-offers/ai-match-offers';
import { BrowseOffers } from './features/browse-offers/browse-offers';
import { MatchOffers } from './features/match-offers/match-offers';
import { ModelUsage } from './features/model-usage/model-usage';
import { Profile } from './features/profile/profile';

export const routes: Routes = [
  { path: '', redirectTo: 'profile', pathMatch: 'full' },
  { path: 'profile', component: Profile },
  { path: 'match-offers', component: MatchOffers },
  { path: 'ai-match-offers', component: AiMatchOffers },
  { path: 'browse-offers', component: BrowseOffers },
  { path: 'model-usage', component: ModelUsage },
];
