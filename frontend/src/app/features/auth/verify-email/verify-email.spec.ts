import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';

import { VerifyEmail } from './verify-email';

async function setup(token: string | null) {
  const router = { navigateByUrl: vi.fn() };
  await TestBed.configureTestingModule({
    imports: [VerifyEmail],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideNoopAnimations(),
      { provide: Router, useValue: router },
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } },
      },
    ],
  }).compileComponents();
  const httpMock = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(VerifyEmail);
  fixture.detectChanges(); // triggers ngOnInit -> verification
  return { fixture, httpMock, router };
}

describe('VerifyEmail', () => {
  it('confirms the emailed token and redirects to the profile signed in', async () => {
    const { httpMock, router } = await setup('good-token');

    const req = httpMock.expectOne((r) => r.url.endsWith('/auth/verify-email'));
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ token: 'good-token' });
    req.flush({ id: '1', email: 'a@b.com' });

    expect(router.navigateByUrl).toHaveBeenCalledWith('/profile');
    httpMock.verify();
  });

  it('shows an invalid-link message on a 400 and does not redirect', async () => {
    const { fixture, httpMock, router } = await setup('bad-token');

    httpMock
      .expectOne((r) => r.url.endsWith('/auth/verify-email'))
      .flush(
        { detail: 'Invalid or expired confirmation link' },
        { status: 400, statusText: 'Bad Request' },
      );

    expect(fixture.componentInstance.status()).toBe('error');
    expect(fixture.componentInstance.error()).toContain('invalid');
    expect(router.navigateByUrl).not.toHaveBeenCalled();
    httpMock.verify();
  });

  it('tells an already-confirmed user to sign in on a 409', async () => {
    const { fixture, httpMock, router } = await setup('used-token');

    httpMock
      .expectOne((r) => r.url.endsWith('/auth/verify-email'))
      .flush(
        { detail: 'Email already confirmed. Please log in.' },
        { status: 409, statusText: 'Conflict' },
      );

    expect(fixture.componentInstance.status()).toBe('error');
    expect(fixture.componentInstance.error()).toContain('already');
    expect(router.navigateByUrl).not.toHaveBeenCalled();
    httpMock.verify();
  });

  it('shows an error without calling the API when the link carries no token', async () => {
    const { fixture, httpMock, router } = await setup(null);

    httpMock.expectNone((r) => r.url.endsWith('/auth/verify-email'));
    expect(fixture.componentInstance.status()).toBe('error');
    expect(router.navigateByUrl).not.toHaveBeenCalled();
    httpMock.verify();
  });
});
