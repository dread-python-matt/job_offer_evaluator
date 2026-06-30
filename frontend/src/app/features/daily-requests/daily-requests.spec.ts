import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';

import { DailyRequests } from './daily-requests';
import { DailyRequestUsage } from '../../core/models/profile.model';

const USAGE: DailyRequestUsage = {
  model: 'gemini-2.5-flash',
  company: 'Google',
  used: 12,
  limit: 500,
  default_limit: 500,
};

describe('DailyRequests', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DailyRequests],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function create(initial: DailyRequestUsage | null) {
    const fixture = TestBed.createComponent(DailyRequests);
    fixture.detectChanges();
    httpMock.expectOne((r) => r.url.endsWith('/usage/daily-requests')).flush(initial);
    fixture.detectChanges();
    return fixture;
  }

  it('shows requests used against the free-tier default cap', () => {
    const fixture = create(USAGE);

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('12');
    expect(text).toContain('500');
    expect(text).toContain('Free-tier default');
  });

  it('shows a guidance message when there is no daily budget for the model', () => {
    const fixture = create(null);

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'No per-day request budget',
    );
  });

  it('adjusts the limit via PUT and reflects the new cap', () => {
    const fixture = create(USAGE);

    fixture.componentInstance.startEdit(USAGE);
    fixture.componentInstance.limitControl.setValue(50);
    fixture.componentInstance.save();

    const req = httpMock.expectOne((r) => r.url.endsWith('/usage/daily-requests'));
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ limit: 50 });
    req.flush({ ...USAGE, limit: 50 });
    fixture.detectChanges();

    expect(fixture.componentInstance.usage()?.limit).toBe(50);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Custom limit');
  });

  it('does not PUT a blank limit', () => {
    const fixture = create(USAGE);

    fixture.componentInstance.startEdit(USAGE);
    fixture.componentInstance.limitControl.setValue(null);
    fixture.componentInstance.save();

    httpMock.expectNone((r) => r.method === 'PUT');
  });

  it('clears the override via PUT with a null limit', () => {
    const fixture = create({ ...USAGE, limit: 50, default_limit: 500 });

    fixture.componentInstance.resetToDefault();

    const req = httpMock.expectOne((r) => r.url.endsWith('/usage/daily-requests'));
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ limit: null });
    req.flush(USAGE);
    fixture.detectChanges();

    expect(fixture.componentInstance.usage()?.limit).toBe(500);
  });

  it('surfaces the server message when an update is rejected', () => {
    const fixture = create(USAGE);

    fixture.componentInstance.startEdit(USAGE);
    fixture.componentInstance.limitControl.setValue(50);
    fixture.componentInstance.save();
    httpMock
      .expectOne((r) => r.url.endsWith('/usage/daily-requests'))
      .flush(
        { detail: 'No daily request budget for the selected model' },
        { status: 404, statusText: 'Not Found' },
      );
    fixture.detectChanges();

    expect(fixture.componentInstance.actionError()).toContain('No daily request budget');
  });

  it('refetches the budget when the host bumps the refresh token', () => {
    const fixture = create(USAGE);

    fixture.componentRef.setInput('refreshToken', 1);
    fixture.detectChanges();

    httpMock
      .expectOne((r) => r.url.endsWith('/usage/daily-requests'))
      .flush({ ...USAGE, model: 'gemini-2.0-flash-lite' });
    fixture.detectChanges();

    expect(fixture.componentInstance.usage()?.model).toBe('gemini-2.0-flash-lite');
  });
});
