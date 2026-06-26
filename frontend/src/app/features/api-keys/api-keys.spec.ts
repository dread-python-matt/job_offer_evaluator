import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';

import { ApiKeys } from './api-keys';

const PROVIDERS = [
  { provider: 'openai', company: 'OpenAI' },
  { provider: 'google', company: 'Google' },
];

function init(
  fixture: ReturnType<typeof TestBed.createComponent<ApiKeys>>,
  httpMock: HttpTestingController,
  keys: unknown[] = [],
) {
  fixture.detectChanges();
  httpMock.expectOne((r) => r.url.endsWith('/api-keys/providers')).flush(PROVIDERS);
  httpMock.expectOne((r) => r.url.endsWith('/api-keys')).flush(keys);
  fixture.detectChanges();
}

describe('ApiKeys', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ApiKeys],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('lists the loaded keys', () => {
    const fixture = TestBed.createComponent(ApiKeys);
    init(fixture, httpMock, [
      { api_provider: 'openai', key_hint: 'sk-…1234', limit_usd: 10, used_usd: 2.5 },
    ]);

    expect(fixture.componentInstance.keys().length).toBe(1);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('sk-…1234');
  });

  it('only offers providers the user has not added yet', () => {
    const fixture = TestBed.createComponent(ApiKeys);
    init(fixture, httpMock, [
      { api_provider: 'openai', key_hint: 'sk-…1234', limit_usd: 10, used_usd: 0 },
    ]);

    const available = fixture.componentInstance.availableProviders().map((p) => p.provider);
    expect(available).toEqual(['google']);
  });

  it('POSTs a new key and appends it to the list', () => {
    const fixture = TestBed.createComponent(ApiKeys);
    init(fixture, httpMock);
    const c = fixture.componentInstance;

    c.providerControl.setValue('openai');
    c.keyControl.setValue('sk-secret-1234');
    c.limitControl.setValue(15);
    c.addKey();

    const req = httpMock.expectOne((r) => r.url.endsWith('/api-keys'));
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ api_provider: 'openai', key: 'sk-secret-1234', limit_usd: 15 });
    req.flush({ api_provider: 'openai', key_hint: 'sk-…1234', limit_usd: 15, used_usd: 0 });

    expect(c.keys().map((k) => k.api_provider)).toEqual(['openai']);
    expect(c.keyControl.value).toBe('');
  });

  it('surfaces the backend message when a key is rejected', () => {
    const fixture = TestBed.createComponent(ApiKeys);
    init(fixture, httpMock);
    const c = fixture.componentInstance;

    c.providerControl.setValue('openai');
    c.keyControl.setValue('sk-bad');
    c.limitControl.setValue(5);
    c.addKey();

    httpMock
      .expectOne((r) => r.url.endsWith('/api-keys'))
      .flush(
        { detail: 'The openai API key was rejected by the provider' },
        { status: 400, statusText: 'Bad Request' },
      );

    expect(c.addError()).toContain('rejected');
    expect(c.keys().length).toBe(0);
  });

  it('does not POST when the form is incomplete', () => {
    const fixture = TestBed.createComponent(ApiKeys);
    init(fixture, httpMock);

    fixture.componentInstance.addKey(); // nothing filled in

    httpMock.expectNone((r) => r.method === 'POST' && r.url.endsWith('/api-keys'));
  });

  it('PATCHes a budget change for a key', () => {
    const fixture = TestBed.createComponent(ApiKeys);
    init(fixture, httpMock, [
      { api_provider: 'openai', key_hint: 'sk-…1234', limit_usd: 10, used_usd: 1 },
    ]);
    const c = fixture.componentInstance;

    c.saveBudget(c.keys()[0], 25);

    const req = httpMock.expectOne((r) => r.url.endsWith('/api-keys/openai'));
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ limit_usd: 25 });
    req.flush({ api_provider: 'openai', key_hint: 'sk-…1234', limit_usd: 25, used_usd: 1 });

    expect(c.keys()[0].limit_usd).toBe(25);
  });

  it('DELETEs a key and removes it from the list', () => {
    const fixture = TestBed.createComponent(ApiKeys);
    init(fixture, httpMock, [
      { api_provider: 'openai', key_hint: 'sk-…1234', limit_usd: 10, used_usd: 1 },
    ]);
    const c = fixture.componentInstance;

    c.removeKey(c.keys()[0]);

    const req = httpMock.expectOne((r) => r.url.endsWith('/api-keys/openai'));
    expect(req.request.method).toBe('DELETE');
    req.flush(null);

    expect(c.keys().length).toBe(0);
  });
});
