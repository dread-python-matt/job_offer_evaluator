import { Routes } from '@angular/router';

import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'profile', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login/login').then((m) => m.Login),
  },
  {
    path: 'register',
    loadComponent: () => import('./features/auth/register/register').then((m) => m.Register),
  },
  {
    path: 'profile',
    canActivate: [authGuard],
    loadComponent: () => import('./features/profile/profile').then((m) => m.Profile),
  },
  {
    path: 'match-offers',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/match-offers/match-offers').then((m) => m.MatchOffers),
  },
  {
    path: 'ai-match-offers',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/ai-match-offers/ai-match-offers').then((m) => m.AiMatchOffers),
  },
  {
    path: 'browse-offers',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/browse-offers/browse-offers').then((m) => m.BrowseOffers),
  },
  {
    path: 'model-usage',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/model-usage/model-usage').then((m) => m.ModelUsage),
  },
];
