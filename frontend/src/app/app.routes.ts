import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'profile', pathMatch: 'full' },
  {
    path: 'profile',
    loadComponent: () => import('./features/profile/profile').then((m) => m.Profile),
  },
  {
    path: 'match-offers',
    loadComponent: () =>
      import('./features/match-offers/match-offers').then((m) => m.MatchOffers),
  },
  {
    path: 'ai-match-offers',
    loadComponent: () =>
      import('./features/ai-match-offers/ai-match-offers').then((m) => m.AiMatchOffers),
  },
  {
    path: 'browse-offers',
    loadComponent: () =>
      import('./features/browse-offers/browse-offers').then((m) => m.BrowseOffers),
  },
  {
    path: 'model-usage',
    loadComponent: () =>
      import('./features/model-usage/model-usage').then((m) => m.ModelUsage),
  },
];
