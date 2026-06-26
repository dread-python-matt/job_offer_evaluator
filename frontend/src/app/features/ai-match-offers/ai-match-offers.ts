import { DecimalPipe, PercentPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { COMMA, ENTER } from '@angular/cdk/keycodes';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule, MatChipInputEvent } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSliderModule } from '@angular/material/slider';
import { HttpErrorResponse } from '@angular/common/http';
import { EMPTY, Subject, catchError, switchMap, tap } from 'rxjs';

import { ApiService } from '../../core/services/api.service';
import { MatchSortBy } from '../../core/models/profile.model';
import { toMatchedOfferRow } from '../../core/utils/offer-row';
import { LEVEL_OPTIONS } from '../../core/constants/offer-levels';
import { AiMatchSortOption, AiMatchStateService } from './ai-match-state.service';

export type { AiMatchSortOption } from './ai-match-state.service';

const AI_MATCH_SORT_OPTION_VALUES: Record<
  AiMatchSortOption,
  { sortBy: MatchSortBy; sortOrder: 'asc' | 'desc' }
> = {
  score: { sortBy: 'score', sortOrder: 'desc' },
  'score-recent': { sortBy: 'score_recent', sortOrder: 'desc' },
  'salary_max-desc': { sortBy: 'salary_max', sortOrder: 'desc' },
  'salary_max-asc': { sortBy: 'salary_max', sortOrder: 'asc' },
  'salary_mid-desc': { sortBy: 'salary_mid', sortOrder: 'desc' },
  'salary_mid-asc': { sortBy: 'salary_mid', sortOrder: 'asc' },
  'salary_min-desc': { sortBy: 'salary_min', sortOrder: 'desc' },
  'salary_min-asc': { sortBy: 'salary_min', sortOrder: 'asc' },
  'recent-desc': { sortBy: 'recent', sortOrder: 'desc' },
  'recent-asc': { sortBy: 'recent', sortOrder: 'asc' },
};

@Component({
  selector: 'app-ai-match-offers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DecimalPipe,
    PercentPipe,
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSliderModule,
  ],
  templateUrl: './ai-match-offers.html',
  styleUrl: './ai-match-offers.scss',
})
export class AiMatchOffers implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly state = inject(AiMatchStateService);

  readonly levelOptions = LEVEL_OPTIONS;
  readonly separatorKeyCodes = [ENTER, COMMA] as const;

  // Transient, per-component state — reset every time the view is entered.
  readonly loading = signal(false);
  readonly totalOffers = signal<number | null>(null);

  // Persistent state, kept in a root-scoped service so the last AI-match result
  // is restored when the user navigates back to this section.
  readonly searched = this.state.searched;
  readonly results = this.state.results;
  readonly usage = this.state.usage;
  readonly techFilter = this.state.techFilter;
  readonly errorMessage = this.state.errorMessage;

  private readonly searchTrigger$ = new Subject<void>();

  readonly filters = this.fb.group({
    offersLimit: this.fb.control<number | null>(null, { validators: [Validators.min(1)] }),
    offersToScore: this.fb.control(20, {
      nonNullable: true,
      validators: [Validators.min(1), Validators.max(50)],
    }),
    minScore: this.fb.control(0.5, { nonNullable: true }),
    aiMinScore: this.fb.control(0.0, { nonNullable: true }),
    location: this.fb.control<string | null>(null),
    minSalary: this.fb.control<number | null>(null, { validators: [Validators.min(0)] }),
    level: this.fb.control<string[]>([], { nonNullable: true }),
    sort: this.fb.control<AiMatchSortOption>('score', { nonNullable: true }),
  });

  constructor() {
    const savedFilters = this.state.filters();
    if (savedFilters) {
      this.filters.setValue(savedFilters);
    }

    this.searchTrigger$
      .pipe(
        tap(() => {
          this.loading.set(true);
          this.errorMessage.set(null);
        }),
        switchMap(() => {
          const {
            offersLimit,
            offersToScore,
            minScore,
            aiMinScore,
            location,
            minSalary,
            level,
            sort,
          } = this.filters.getRawValue();
          const trimmedLocation = location?.trim() || null;
          const { sortBy, sortOrder } = AI_MATCH_SORT_OPTION_VALUES[sort];

          return this.api.getProfile().pipe(
            switchMap((candidate) =>
              this.api.matchOffersWithAi({
                candidate,
                offersLimit,
                minScore,
                location: trimmedLocation,
                minSalary,
                level,
                tech: this.techFilter(),
                sortBy,
                sortOrder,
                offersToScore,
                aiMinScore,
              }),
            ),
            catchError((err: HttpErrorResponse) => {
              this.loading.set(false);
              let message: string;
              if (err.status === 404) {
                message = 'Save your profile before matching offers.';
              } else if (err.status === 503 && err.error?.detail) {
                message = err.error.detail;
              } else {
                message = 'Failed to load AI-matched offers.';
              }
              this.errorMessage.set(message);
              return EMPTY;
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((result) => {
        this.results.set(result.matches.map(toMatchedOfferRow));
        if (result.usage != null) {
          this.usage.set(result.usage);
        }
        this.loading.set(false);
        this.searched.set(true);
      });
  }

  ngOnInit(): void {
    this.api.getOffersCount().subscribe((total) => this.totalOffers.set(total));
  }

  addTech(event: MatChipInputEvent): void {
    const value = (event.value || '').trim();
    if (value) {
      this.techFilter.update((techs) => [...techs, value]);
    }
    event.chipInput.clear();
  }

  removeTech(tech: string): void {
    this.techFilter.update((techs) => techs.filter((t) => t !== tech));
  }

  search(): void {
    if (this.filters.invalid) {
      this.filters.markAllAsTouched();
      return;
    }
    this.state.filters.set(this.filters.getRawValue());
    this.searchTrigger$.next();
  }
}
