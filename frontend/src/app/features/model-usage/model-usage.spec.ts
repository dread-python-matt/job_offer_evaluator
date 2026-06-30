import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';

import { ModelUsage } from './model-usage';
import { ModelUsageSummaryItem } from '../../core/models/profile.model';

const MODELS = {
  companies: [{ name: 'OpenAI', models: ['gpt-4o-mini'] }],
  active: { model: 'gpt-4o-mini', company: 'OpenAI' },
};

function init(
  fixture: ReturnType<typeof TestBed.createComponent<ModelUsage>>,
  httpMock: HttpTestingController,
  summaries: ModelUsageSummaryItem[] = [],
) {
  fixture.detectChanges();
  httpMock.expectOne((r) => r.url.endsWith('/usage/summary')).flush(summaries);
  httpMock.expectOne((r) => r.url.endsWith('/config/models')).flush(MODELS);
  httpMock.expectOne((r) => r.url.endsWith('/usage/org-spend')).flush(null);
  // The embedded <app-daily-requests> child loads its own data.
  httpMock.expectOne((r) => r.url.endsWith('/usage/daily-requests')).flush(null);
  // The embedded <app-api-keys> child loads its own data.
  httpMock.expectOne((r) => r.url.endsWith('/api-keys/providers')).flush([]);
  httpMock.expectOne((r) => r.url.endsWith('/api-keys')).flush([]);
  // The embedded <app-admin-key> child loads its own data.
  httpMock.expectOne((r) => r.url.endsWith('/admin-key')).flush(null);
  fixture.detectChanges();
}

describe('ModelUsage', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ModelUsage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('loads the active model and usage summary', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock);

    expect(fixture.componentInstance.currentModel()?.model).toBe('gpt-4o-mini');
    expect(fixture.componentInstance.availableModels()?.companies.length).toBe(1);
  });

  it('does not load the retired global budget cost endpoint', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock);

    httpMock.expectNone((r) => r.url.endsWith('/usage/cost'));
  });

  it('shows the organization spend (admin key) when available', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    fixture.detectChanges();
    httpMock.expectOne((r) => r.url.endsWith('/usage/summary')).flush([]);
    httpMock.expectOne((r) => r.url.endsWith('/config/models')).flush(MODELS);
    httpMock
      .expectOne((r) => r.url.endsWith('/usage/org-spend'))
      .flush({ spend_usd: 4.2, since: '2026-06-25T00:00:00Z' });
    httpMock.expectOne((r) => r.url.endsWith('/usage/daily-requests')).flush(null);
    httpMock.expectOne((r) => r.url.endsWith('/api-keys/providers')).flush([]);
    httpMock.expectOne((r) => r.url.endsWith('/api-keys')).flush([]);
    httpMock.expectOne((r) => r.url.endsWith('/admin-key')).flush(null);
    fixture.detectChanges();

    expect(fixture.componentInstance.orgSpend()?.spend_usd).toBe(4.2);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('$4.20');
  });

  it('shows an estimated OpenAI cost total (and per-model $) from the usage summary', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock, [
      {
        company: 'OpenAI',
        model: 'gpt-4o-mini',
        input_tokens: 1000,
        output_tokens: 200,
        cost_usd: 0.1234,
        limits: null,
      },
    ]);

    expect(fixture.componentInstance.estimatedOpenAiCost()).toBeCloseTo(0.1234);
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('$0.12'); // headline estimated total (1.2-2)
    expect(text).toContain('$0.1234'); // per-model estimate (1.2-4)
    expect(text.toLowerCase()).toContain('estimated');
  });

  it('does not show a $ cost for Gemini models (Gemini interface unchanged)', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock, [
      {
        company: 'Google',
        model: 'gemini-2.0-flash',
        input_tokens: 1000,
        output_tokens: 200,
        cost_usd: 0.5,
        limits: null,
      },
    ]);

    expect(fixture.componentInstance.hasOpenAiUsage()).toBe(false);
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).not.toContain('$0.50'); // Gemini cost is never rendered
    expect(text).not.toContain('est.');
  });
});
