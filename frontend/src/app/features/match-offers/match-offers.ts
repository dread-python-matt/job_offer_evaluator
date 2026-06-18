import { PercentPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSliderModule } from '@angular/material/slider';
import { MatSnackBar } from '@angular/material/snack-bar';
import { HttpErrorResponse } from '@angular/common/http';
import { switchMap } from 'rxjs';

import { ApiService } from '../../core/services/api.service';
import { MatchedOffer } from '../../core/models/profile.model';

interface MatchedOfferRow {
  title: string;
  company: string;
  score: number;
  scoreLabel: string;
  scoreClass: 'score-high' | 'score-medium' | 'score-low';
  matchedSkills: string[];
  link: string;
}

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
    MatSliderModule,
  ],
  templateUrl: './match-offers.html',
  styleUrl: './match-offers.scss',
})
export class MatchOffers {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);

  readonly loading = signal(false);
  readonly searched = signal(false);
  readonly results = signal<MatchedOfferRow[]>([]);

  readonly filters = this.fb.group({
    offersLimit: this.fb.control<number | null>(null, { validators: [Validators.min(1)] }),
    minScore: this.fb.control(0.5, { nonNullable: true }),
  });

  search(): void {
    if (this.filters.invalid) {
      this.filters.markAllAsTouched();
      return;
    }

    const { offersLimit, minScore } = this.filters.getRawValue();
    this.loading.set(true);
    this.api
      .getProfile()
      .pipe(switchMap((candidate) => this.api.matchOffers(candidate, offersLimit, minScore)))
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
    };
  }

  private scoreClass(score: number): MatchedOfferRow['scoreClass'] {
    if (score >= 0.7) return 'score-high';
    if (score >= 0.4) return 'score-medium';
    return 'score-low';
  }
}
