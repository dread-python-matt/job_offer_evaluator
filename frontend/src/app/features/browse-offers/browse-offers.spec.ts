import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';

import { BrowseOffers } from './browse-offers';
import { OffersPage } from '../../core/models/profile.model';

describe('BrowseOffers', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BrowseOffers],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  function expectOffersRequest(params: Record<string, string>, page: OffersPage): void {
    const req = httpMock.expectOne(
      (request) =>
        request.url.endsWith('/offers') &&
        Object.entries(params).every(([key, value]) => request.params.get(key) === value),
    );
    req.flush(page);
  }

  it('loads the first page on init and renders the offers', async () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();

    expectOffersRequest(
      { limit: '20', offset: '0' },
      {
        offers: [
          {
            link: 'https://example.com/a',
            title: 'Backend Engineer',
            company: 'Acme',
            locations: ['Warsaw'],
            salaries: [
              { contract_type: 'permanent', min: 20000, max: 25000, net_monthly: null, currency: 'PLN', period: 'month' },
            ],
            tech_stack: ['Python'],
            tech_stack_nice_to_have: [],
            expired: false,
            expires: null,
            levels: ['Mid'],
            published: '2026-06-01',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      },
    );
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Backend Engineer');
    expect(compiled.textContent).toContain('Acme');
    expect(compiled.textContent).toContain('Mid');
    expect(compiled.textContent).toContain('20000 - 25000 PLN/month');
  });

  it('requests the next offset when the paginator page changes', () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();
    expectOffersRequest({ limit: '20', offset: '0' }, { offers: [], total: 50, limit: 20, offset: 0 });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.onPage({ pageIndex: 1, pageSize: 20, length: 50 });

    expectOffersRequest(
      { limit: '20', offset: '20' },
      { offers: [], total: 50, limit: 20, offset: 20 },
    );
  });

  it('shows an error message and does not crash when the request fails', () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();

    const req = httpMock.expectOne((request) => request.url.endsWith('/offers'));
    req.flush('error', { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(fixture.componentInstance.loading()).toBe(false);
  });

  it('applies filters and resets to the first page', () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();
    expectOffersRequest({ limit: '20', offset: '0' }, { offers: [], total: 0, limit: 20, offset: 0 });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.techFilter.set(['Python']);
    component.filters.setValue({
      location: 'Warsaw',
      minSalary: 15000,
      search: 'Backend',
      level: ['Mid'],
      sort: 'recent-desc',
    });
    component.applyFilters();

    expectOffersRequest(
      {
        limit: '20',
        offset: '0',
        location: 'Warsaw',
        min_salary: '15000',
        tech: 'Python',
        search: 'Backend',
        level: 'Mid',
      },
      { offers: [], total: 0, limit: 20, offset: 0 },
    );
  });

  it('clears filters and reloads without filter params', () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();
    expectOffersRequest({ limit: '20', offset: '0' }, { offers: [], total: 0, limit: 20, offset: 0 });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.filters.setValue({
      location: 'Warsaw',
      minSalary: 15000,
      search: null,
      level: ['Mid'],
      sort: 'recent-desc',
    });
    component.applyFilters();
    httpMock.expectOne((request) => request.url.endsWith('/offers')).flush({
      offers: [],
      total: 0,
      limit: 20,
      offset: 0,
    });

    component.clearFilters();

    const req = httpMock.expectOne((request) => request.url.endsWith('/offers'));
    expect(req.request.params.get('location')).toBeNull();
    expect(req.request.params.get('min_salary')).toBeNull();
    expect(req.request.params.get('level')).toBeNull();
    req.flush({ offers: [], total: 0, limit: 20, offset: 0 });
  });

  it('preserves active filters when the paginator page changes', () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();
    expectOffersRequest({ limit: '20', offset: '0' }, { offers: [], total: 50, limit: 20, offset: 0 });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.filters.setValue({ location: 'Warsaw', minSalary: null, search: null, level: [], sort: 'recent-desc' });
    component.applyFilters();
    httpMock.expectOne((request) => request.url.endsWith('/offers')).flush({
      offers: [],
      total: 50,
      limit: 20,
      offset: 0,
    });

    component.onPage({ pageIndex: 1, pageSize: 20, length: 50 });

    expectOffersRequest(
      { limit: '20', offset: '20', location: 'Warsaw' },
      { offers: [], total: 50, limit: 20, offset: 20 },
    );
  });

  it('sends sort_by and sort_order when a sort option is chosen and resets to the first page', () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();
    expectOffersRequest({ limit: '20', offset: '0' }, { offers: [], total: 50, limit: 20, offset: 0 });
    fixture.detectChanges();

    const component = fixture.componentInstance;
    component.onPage({ pageIndex: 1, pageSize: 20, length: 50 });
    expectOffersRequest({ limit: '20', offset: '20' }, { offers: [], total: 50, limit: 20, offset: 20 });

    component.filters.controls.sort.setValue('salary-desc');
    component.onSortChange();

    expectOffersRequest(
      { limit: '20', offset: '0', sort_by: 'salary', sort_order: 'desc' },
      { offers: [], total: 50, limit: 20, offset: 0 },
    );
  });

  it('sends sort_by=recent with an ascending order', () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();
    expectOffersRequest({ limit: '20', offset: '0' }, { offers: [], total: 0, limit: 20, offset: 0 });
    fixture.detectChanges();

    fixture.componentInstance.filters.controls.sort.setValue('recent-asc');
    fixture.componentInstance.onSortChange();

    expectOffersRequest(
      { limit: '20', offset: '0', sort_by: 'recent', sort_order: 'asc' },
      { offers: [], total: 0, limit: 20, offset: 0 },
    );
  });

  it('sends sort_by=recent desc by default on init', () => {
    const fixture = TestBed.createComponent(BrowseOffers);
    fixture.detectChanges();

    const req = httpMock.expectOne((request) => request.url.endsWith('/offers'));
    expect(req.request.params.get('sort_by')).toBe('recent');
    expect(req.request.params.get('sort_order')).toBe('desc');
    req.flush({ offers: [], total: 0, limit: 20, offset: 0 });
  });
});
