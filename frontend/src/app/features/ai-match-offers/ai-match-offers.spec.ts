import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';

import { AiMatchOffers } from './ai-match-offers';

const PROFILE = {
  summary: 'Dev',
  skills: [{ name: 'Python', rating: 5 }],
  projects: [],
  experience: [],
};

const OFFER = {
  link: 'https://example.com/job1',
  title: 'AI Architect',
  company: 'DeepTech',
  score: 0.9,
  matched_skills: ['Python'],
  locations: ['Remote'],
  salaries: [],
  expired: false,
  expires: null,
  levels: ['Senior'],
  published: '2026-06-20',
};

function flush(fixture: ReturnType<typeof TestBed.createComponent<AiMatchOffers>>, httpMock: HttpTestingController, matches = [OFFER], usage: { input_tokens: number; output_tokens: number } | null = null) {
  fixture.componentInstance.search();
  httpMock.expectOne((req) => req.url.endsWith('/profile')).flush(PROFILE);
  const req = httpMock.expectOne((req) => req.url.endsWith('/offers/match/ai'));
  req.flush({ matches, usage });
  fixture.detectChanges();
  return req;
}

describe('AiMatchOffers', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AiMatchOffers],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('fetches offers count on init', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 42 });
  });

  it('posts to /offers/match/ai with default offers_to_score on search', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 10 });

    const req = flush(fixture, httpMock, []);
    expect(req.request.body['offers_to_score']).toBe(20);
  });

  it('sends the offers_to_score value from the form control', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    fixture.componentInstance.filters.controls.offersToScore.setValue(35);
    const req = flush(fixture, httpMock, []);
    expect(req.request.body['offers_to_score']).toBe(35);
  });

  it('sends level as an array', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    fixture.componentInstance.filters.controls.level.setValue(['Mid', 'Senior']);
    const req = flush(fixture, httpMock, []);
    expect(req.request.body['level']).toEqual(['Mid', 'Senior']);
  });

  it('sends empty level array when no levels selected', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    const req = flush(fixture, httpMock, []);
    expect(req.request.body['level']).toEqual([]);
  });

  it('sends added tech chips in the request body', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    fixture.componentInstance.addTech({ value: 'Python', chipInput: { clear: () => {} } } as any);
    fixture.componentInstance.addTech({ value: 'FastAPI', chipInput: { clear: () => {} } } as any);
    const req = flush(fixture, httpMock, []);
    expect(req.request.body['tech']).toEqual(['Python', 'FastAPI']);
  });

  it('removes a tech chip', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    fixture.componentInstance.addTech({ value: 'Python', chipInput: { clear: () => {} } } as any);
    fixture.componentInstance.addTech({ value: 'FastAPI', chipInput: { clear: () => {} } } as any);
    fixture.componentInstance.removeTech('Python');

    expect(fixture.componentInstance.techFilter()).toEqual(['FastAPI']);
  });

  it('ignores blank tech input', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    fixture.componentInstance.addTech({ value: '  ', chipInput: { clear: () => {} } } as any);
    expect(fixture.componentInstance.techFilter()).toEqual([]);
  });

  it('renders matched offers after a successful search', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    flush(fixture, httpMock);

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('AI Architect');
    expect(el.textContent).toContain('DeepTech');
    expect(el.textContent).toContain('90%');
  });

  it('does not post when the form is invalid', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    fixture.componentInstance.filters.controls.offersLimit.setValue(-1);
    fixture.componentInstance.search();

    httpMock.expectNone((req) => req.url.endsWith('/offers/match/ai'));
  });

  it('shows usage stats after a successful search when usage is returned', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    flush(fixture, httpMock, [], { input_tokens: 1500, output_tokens: 300 });

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.usage-stats')).not.toBeNull();
    expect(el.textContent).toContain('1,500');
    expect(el.textContent).toContain('300');
    expect(el.textContent).toContain('1,800');
  });

  it('shows usage stats section with dashes before any search', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.usage-stats')).not.toBeNull();
    expect(el.querySelector('.usage-stats')!.textContent).toContain('—');
  });

  it('keeps previous usage when a subsequent search returns null usage', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    flush(fixture, httpMock, [], { input_tokens: 100, output_tokens: 50 });
    flush(fixture, httpMock, [], null);

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.usage-stats')).not.toBeNull();
    expect(el.textContent).toContain('100');
    expect(el.textContent).toContain('50');
  });

  it('keeps usage stats visible while a new search is loading', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    flush(fixture, httpMock, [], { input_tokens: 100, output_tokens: 50 });

    fixture.componentInstance.search();
    httpMock.expectOne((req) => req.url.endsWith('/profile')).flush(PROFILE);
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.usage-stats')).not.toBeNull();

    httpMock.expectOne((req) => req.url.endsWith('/offers/match/ai')).flush({ matches: [], usage: null });
    fixture.detectChanges();
  });


  it('shows inline error block when the AI match request fails', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    fixture.componentInstance.search();
    httpMock.expectOne((req) => req.url.endsWith('/profile')).flush(PROFILE);
    httpMock
      .expectOne((req) => req.url.endsWith('/offers/match/ai'))
      .flush({ detail: 'Gemini API quota exceeded' }, { status: 503, statusText: 'Service Unavailable' });
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.error-block')).not.toBeNull();
    expect(el.textContent).toContain('Gemini API quota exceeded');
    expect(el.querySelector('.search-summary')).toBeNull();
  });

  it('clears the error block on the next successful search', () => {
    const fixture = TestBed.createComponent(AiMatchOffers);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url.endsWith('/offers/count')).flush({ total: 5 });

    fixture.componentInstance.search();
    httpMock.expectOne((req) => req.url.endsWith('/profile')).flush(PROFILE);
    httpMock
      .expectOne((req) => req.url.endsWith('/offers/match/ai'))
      .flush({ detail: 'error' }, { status: 503, statusText: 'Service Unavailable' });
    fixture.detectChanges();

    flush(fixture, httpMock, [OFFER], { input_tokens: 100, output_tokens: 50 });

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.error-block')).toBeNull();
    expect(el.querySelector('.usage-stats')).not.toBeNull();
  });
});
