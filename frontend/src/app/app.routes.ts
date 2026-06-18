import { Routes } from '@angular/router';

import { MatchOffers } from './features/match-offers/match-offers';
import { Profile } from './features/profile/profile';

export const routes: Routes = [
  { path: '', redirectTo: 'profile', pathMatch: 'full' },
  { path: 'profile', component: Profile },
  { path: 'match-offers', component: MatchOffers },
];
