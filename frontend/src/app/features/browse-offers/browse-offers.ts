import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar } from '@angular/material/snack-bar';

import { ApiService } from '../../core/services/api.service';
import { Offer, OfferFilters, SortBy, SortOrder } from '../../core/models/profile.model';
import { formatSalaries } from '../../core/utils/offer-format';
import { LEVEL_OPTIONS } from '../../core/constants/offer-levels';

export type SortOption = 'relevance' | 'salary-desc' | 'salary-asc' | 'recent-desc' | 'recent-asc';

const SORT_OPTION_VALUES: Record<SortOption, { sortBy: SortBy | null; sortOrder: SortOrder }> = {
  relevance: { sortBy: null, sortOrder: 'desc' },
  'salary-desc': { sortBy: 'salary', sortOrder: 'desc' },
  'salary-asc': { sortBy: 'salary', sortOrder: 'asc' },
  'recent-desc': { sortBy: 'recent', sortOrder: 'desc' },
  'recent-asc': { sortBy: 'recent', sortOrder: 'asc' },
};

@Component({
  selector: 'app-browse-offers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatPaginatorModule,
    MatProgressSpinnerModule,
    MatSelectModule,
  ],
  templateUrl: './browse-offers.html',
  styleUrl: './browse-offers.scss',
})
export class BrowseOffers implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);

  readonly levelOptions = LEVEL_OPTIONS;

  readonly loading = signal(false);
  readonly offers = signal<Offer[]>([]);
  readonly total = signal(0);
  readonly pageIndex = signal(0);
  readonly pageSize = signal(20);
  readonly sort = signal<SortOption>('recent-desc');

  readonly filters = this.fb.group({
    location: this.fb.control<string | null>(null),
    minSalary: this.fb.control<number | null>(null, { validators: [Validators.min(0)] }),
    tech: this.fb.control<string | null>(null),
    search: this.fb.control<string | null>(null),
    level: this.fb.control<string | null>(null),
  });

  ngOnInit(): void {
    this.loadPage();
  }

  onSortChange(sort: SortOption): void {
    this.sort.set(sort);
    this.pageIndex.set(0);
    this.loadPage();
  }

  salaryLabel(offer: Offer): string | null {
    return formatSalaries(offer.salaries);
  }

  onPage(event: PageEvent): void {
    this.pageIndex.set(event.pageIndex);
    this.pageSize.set(event.pageSize);
    this.loadPage();
  }

  applyFilters(): void {
    if (this.filters.invalid) {
      this.filters.markAllAsTouched();
      return;
    }
    this.pageIndex.set(0);
    this.loadPage();
  }

  clearFilters(): void {
    this.filters.reset();
    this.pageIndex.set(0);
    this.loadPage();
  }

  private loadPage(): void {
    this.loading.set(true);
    this.api.getOffers(this.pageSize(), this.pageIndex() * this.pageSize(), this.currentFilters()).subscribe({
      next: (page) => {
        this.offers.set(page.offers);
        this.total.set(page.total);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snackBar.open('Failed to load offers.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  private currentFilters(): OfferFilters {
    const { location, minSalary, tech, search, level } = this.filters.getRawValue();
    const { sortBy, sortOrder } = SORT_OPTION_VALUES[this.sort()];
    return {
      location: location?.trim() || null,
      minSalary,
      tech: tech?.trim() || null,
      search: search?.trim() || null,
      level: level || null,
      sortBy,
      sortOrder,
    };
  }
}
