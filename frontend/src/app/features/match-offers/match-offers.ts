import { PercentPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
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
import { MatSnackBar } from '@angular/material/snack-bar';
import { HttpErrorResponse } from '@angular/common/http';
import { switchMap } from 'rxjs';

import { ApiService } from '../../core/services/api.service';
import { MatchedOffer, MatchSortBy } from '../../core/models/profile.model';
import { formatSalaries } from '../../core/utils/offer-format';
import { LEVEL_OPTIONS } from '../../core/constants/offer-levels';

interface MatchedOfferRow {
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

export type MatchSortOption =
  | 'score'
  | 'score-recent'
  | 'salary-desc'
  | 'salary-asc'
  | 'recent-desc'
  | 'recent-asc';

const MATCH_SORT_OPTION_VALUES: Record<
  MatchSortOption,
  { sortBy: MatchSortBy; sortOrder: 'asc' | 'desc' }
> = {
  score: { sortBy: 'score', sortOrder: 'desc' },
  'score-recent': { sortBy: 'score_recent', sortOrder: 'desc' },
  'salary-desc': { sortBy: 'salary', sortOrder: 'desc' },
  'salary-asc': { sortBy: 'salary', sortOrder: 'asc' },
  'recent-desc': { sortBy: 'recent', sortOrder: 'desc' },
  'recent-asc': { sortBy: 'recent', sortOrder: 'asc' },
};

@Component({
  selector: 'app-match-offers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
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
  templateUrl: './match-offers.html',
  styleUrl: './match-offers.scss',
})
export class MatchOffers implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);

  readonly levelOptions = LEVEL_OPTIONS;
  readonly separatorKeyCodes = [ENTER, COMMA] as const;

  readonly loading = signal(false);
  readonly searched = signal(false);
  readonly results = signal<MatchedOfferRow[]>([]);
  readonly totalOffers = signal<number | null>(null);
  readonly techFilter = signal<string[]>([]);

  ngOnInit(): void {
    this.api.getOffersCount().subscribe((total) => this.totalOffers.set(total));
  }

  readonly filters = this.fb.group({
    offersLimit: this.fb.control<number | null>(null, { validators: [Validators.min(1)] }),
    minScore: this.fb.control(0.5, { nonNullable: true }),
    location: this.fb.control<string | null>(null),
    minSalary: this.fb.control<number | null>(null, { validators: [Validators.min(0)] }),
    level: this.fb.control<string[]>([], { nonNullable: true }),
    sort: this.fb.control<MatchSortOption>('score', { nonNullable: true }),
  });

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

    const { offersLimit, minScore, location, minSalary, level, sort } = this.filters.getRawValue();
    const trimmedLocation = location?.trim() || null;
    const { sortBy, sortOrder } = MATCH_SORT_OPTION_VALUES[sort];
    this.loading.set(true);
    this.api
      .getProfile()
      .pipe(
        switchMap((candidate) =>
          this.api.matchOffers(
            candidate,
            offersLimit,
            minScore,
            trimmedLocation,
            minSalary,
            level,
            this.techFilter(),
            sortBy,
            sortOrder,
          ),
        ),
      )
      .subscribe({
        next: (matches) => {
          this.results.set(matches.map((match) => this.toRow(match)));
          this.loading.set(false);
          this.searched.set(true);
        },
        error: (err: HttpErrorResponse) => {
          this.loading.set(false);
          const message =
            err.status === 404
              ? 'Save your profile before matching offers.'
              : 'Failed to load matched offers.';
          this.snackBar.open(message, 'Dismiss', { duration: 4000 });
        },
      });
  }

  private toRow(match: MatchedOffer): MatchedOfferRow {
    return {
      title: match.title,
      company: match.company,
      score: match.score,
      scoreLabel: `${Math.round(match.score * 100)}%`,
      scoreClass: this.scoreClass(match.score),
      matchedSkills: [...match.matched_skills].sort(),
      link: match.link,
      locations: match.locations,
      salaryLabel: formatSalaries(match.salaries),
      levels: match.levels,
    };
  }

  private scoreClass(score: number): MatchedOfferRow['scoreClass'] {
    if (score >= 0.7) return 'score-high';
    if (score >= 0.4) return 'score-medium';
    return 'score-low';
  }
}
