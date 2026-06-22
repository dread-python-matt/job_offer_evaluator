import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ApiService } from '../../core/services/api.service';
import { CurrentModelConfig, ModelUsageSummaryItem } from '../../core/models/profile.model';

@Component({
  selector: 'app-model-usage',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DecimalPipe,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  templateUrl: './model-usage.html',
  styleUrl: './model-usage.scss',
})
export class ModelUsage implements OnInit {
  private readonly api = inject(ApiService);

  readonly loading = signal(false);
  readonly error = signal(false);
  readonly items = signal<ModelUsageSummaryItem[]>([]);
  readonly currentModel = signal<CurrentModelConfig | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(false);
    forkJoin({
      summary: this.api.getUsageSummary(),
      model: this.api.getCurrentModel(),
    }).subscribe({
      next: ({ summary, model }) => {
        this.items.set(summary);
        this.currentModel.set(model);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }

  total(item: ModelUsageSummaryItem): number {
    return item.input_tokens + item.output_tokens;
  }

  inputPct(item: ModelUsageSummaryItem): number {
    const t = this.total(item);
    return t === 0 ? 50 : (item.input_tokens / t) * 100;
  }

  isActive(item: ModelUsageSummaryItem): boolean {
    const cm = this.currentModel();
    return cm != null && cm.model === item.model;
  }
}
