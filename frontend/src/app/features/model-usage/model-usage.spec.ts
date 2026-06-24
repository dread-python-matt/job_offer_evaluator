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
  cost: { cost_usd: number; limit_usd: number } | null = { cost_usd: 1.25, limit_usd: 5 },
) {
  fixture.detectChanges();
  httpMock.expectOne((r) => r.url.endsWith('/usage/summary')).flush([]);
  httpMock.expectOne((r) => r.url.endsWith('/config/models')).flush(MODELS);
  httpMock.expectOne((r) => r.url.endsWith('/usage/cost')).flush(cost);
  fixture.detectChanges();
}

describe('ModelUsage budget', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ModelUsage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('prefills the limit control from the loaded budget', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock);

    expect(fixture.componentInstance.limitControl.value).toBe(5);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('$1.2500');
  });

  it('PUTs the new limit and reflects the returned budget', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock);

    fixture.componentInstance.limitControl.setValue(20);
    fixture.componentInstance.saveLimit();

    const req = httpMock.expectOne((r) => r.url.endsWith('/usage/limit'));
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ limit_usd: 20 });
    req.flush({ limit_usd: 20, used_usd: 1.25, tracking_since: '2026-06-20T00:00:00Z' });
    fixture.detectChanges();

    expect(fixture.componentInstance.dailyCost()).toEqual({ cost_usd: 1.25, limit_usd: 20 });
    expect(fixture.componentInstance.trackingSince()).toBe('2026-06-20T00:00:00Z');
    expect(fixture.componentInstance.budgetBusy()).toBe(false);
  });

  it('does not PUT when the limit is invalid', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock);

    fixture.componentInstance.limitControl.setValue(-5);
    fixture.componentInstance.saveLimit();

    httpMock.expectNone((r) => r.url.endsWith('/usage/limit'));
  });

  it('POSTs a reset and updates the spend to the returned value', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock);

    fixture.componentInstance.resetUsage();

    const req = httpMock.expectOne((r) => r.url.endsWith('/usage/reset'));
    expect(req.request.method).toBe('POST');
    req.flush({ limit_usd: 5, used_usd: 0, tracking_since: '2026-06-24T10:00:00Z' });
    fixture.detectChanges();

    expect(fixture.componentInstance.dailyCost()).toEqual({ cost_usd: 0, limit_usd: 5 });
    expect(fixture.componentInstance.trackingSince()).toBe('2026-06-24T10:00:00Z');
  });

  it('surfaces an error when a budget update fails', () => {
    const fixture = TestBed.createComponent(ModelUsage);
    init(fixture, httpMock);

    fixture.componentInstance.resetUsage();
    httpMock
      .expectOne((r) => r.url.endsWith('/usage/reset'))
      .flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(fixture.componentInstance.budgetError()).not.toBeNull();
    expect(fixture.componentInstance.budgetBusy()).toBe(false);
  });
});
