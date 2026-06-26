import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';
import { Register } from './register';

async function setup() {
  await TestBed.configureTestingModule({
    imports: [Register],
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideNoopAnimations(),
      provideRouter([]),
    ],
  }).compileComponents();
  const httpMock = TestBed.inject(HttpTestingController);
  const auth = TestBed.inject(AuthService);
  const router = TestBed.inject(Router);
  const navigate = vi.spyOn(router, 'navigateByUrl');
  const fixture = TestBed.createComponent(Register);
  fixture.detectChanges();
  return { fixture, httpMock, router: { navigateByUrl: navigate }, auth };
}

function fillValid(component: Register): void {
  component.form.setValue({
    email: 'a@b.com',
    password: 'longenoughpw',
    confirmPassword: 'longenoughpw',
  });
}

describe('Register', () => {
  it('does not submit when the form is invalid', async () => {
    const { fixture, httpMock } = await setup();

    fixture.componentInstance.submit();

    httpMock.expectNone((r) => r.url.endsWith('/auth/register'));
    httpMock.verify();
  });

  it('shows a "check your email" message on a 202 without logging in or navigating', async () => {
    const { fixture, httpMock, router, auth } = await setup();
    fillValid(fixture.componentInstance);

    fixture.componentInstance.submit();

    const req = httpMock.expectOne((r) => r.url.endsWith('/auth/register'));
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      email: 'a@b.com',
      password: 'longenoughpw',
      confirm_password: 'longenoughpw',
    });
    // Registration does not issue a session — the account stays unverified.
    req.flush({ email: 'a@b.com', message: 'Check your email to confirm your account.' });

    expect(fixture.componentInstance.submitted()).toBe(true);
    expect(auth.isAuthenticated()).toBe(false);
    expect(router.navigateByUrl).not.toHaveBeenCalled();
    httpMock.verify();
  });

  it('shows an already-registered message on a 409', async () => {
    const { fixture, httpMock } = await setup();
    fillValid(fixture.componentInstance);

    fixture.componentInstance.submit();

    httpMock
      .expectOne((r) => r.url.endsWith('/auth/register'))
      .flush({ detail: 'Email already registered' }, { status: 409, statusText: 'Conflict' });

    expect(fixture.componentInstance.submitted()).toBe(false);
    expect(fixture.componentInstance.error()).toContain('already registered');
    httpMock.verify();
  });

  it('shows a generic error on other failures', async () => {
    const { fixture, httpMock } = await setup();
    fillValid(fixture.componentInstance);

    fixture.componentInstance.submit();

    httpMock
      .expectOne((r) => r.url.endsWith('/auth/register'))
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });

    expect(fixture.componentInstance.submitted()).toBe(false);
    expect(fixture.componentInstance.error()).toBeTruthy();
    httpMock.verify();
  });
});
