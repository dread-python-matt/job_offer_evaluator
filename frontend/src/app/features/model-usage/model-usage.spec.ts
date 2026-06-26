import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';

import { ModelUsage } from './model-usage';

const MODELS = {
  companies: [{ name: 'OpenAI', models: ['gpt-4o-mini'] }],
  active: { model: 'gpt-4o-mini', company: 'OpenAI' },
};

function init(
  fixture: ReturnType<typeof TestBed.createComponent<ModelUsage>>,
  httpMock: HttpTestingController,
) {
  fixture.detectChanges();
  httpMock.expectOne((r) => r.url.endsWith('/usage/summary')).flush([]);
  httpMock.expectOne((r) => r.url.endsWith('/config/models')).flush(MODELS);
  httpMock.expectOne((r) => r.url.endsWith('/usage/org-spend')).flush(null);
  // The embedded <app-api-keys> child loads its own data.
  httpMock.expectOne((r) => r.url.endsWith('/api-keys/providers')).flush([]);
  httpMock.expectOne((r) => r.url.endsWith('/api-keys')).flush([]);
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
    httpMock.expectOne((r) => r.url.endsWith('/api-keys/providers')).flush([]);
    httpMock.expectOne((r) => r.url.endsWith('/api-keys')).flush([]);
    fixture.detectChanges();

    expect(fixture.componentInstance.orgSpend()?.spend_usd).toBe(4.2);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('$4.20');
  });
});
