import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TestBed } from '@angular/core/testing';

import { AdminKey } from './admin-key';

const SAVED = { key_hint: 'sk-…1234', created_at: '2026-06-30T00:00:00Z' };

describe('AdminKey', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminKey],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideNoopAnimations()],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  function create(initial: typeof SAVED | null) {
    const fixture = TestBed.createComponent(AdminKey);
    fixture.detectChanges();
    httpMock.expectOne((r) => r.url.endsWith('/admin-key')).flush(initial);
    fixture.detectChanges();
    return fixture;
  }

  it('shows the masked begin…end hint, a Delete button, and no input when a key is saved', () => {
    const fixture = create(SAVED);

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('sk-…1234'); // begin…end, middle masked
    expect(el.textContent).toContain('Delete'); // labelled delete button
    expect(el.querySelector('input')).toBeNull(); // can't enter a second key while one exists
  });

  it('shows the add form when no admin key is saved', () => {
    const fixture = create(null);

    expect((fixture.nativeElement as HTMLElement).querySelector('input')).not.toBeNull();
  });

  it('shows the actual spend this month when a spend figure is provided', () => {
    const fixture = create(SAVED);
    fixture.componentRef.setInput('spend', {
      spend_usd: 12.34,
      since: '2026-06-01T00:00:00Z',
    });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Spent this month');
    expect(text).toContain('$12.34');
  });

  it('shows no spend figure when none is provided', () => {
    const fixture = create(SAVED);

    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Spent this month');
  });

  it('saves a key via PUT, emits changed, and shows the masked hint', () => {
    const fixture = create(null);
    let changed = 0;
    fixture.componentInstance.changed.subscribe(() => (changed += 1));

    fixture.componentInstance.keyControl.setValue('sk-admin-secret-1234');
    fixture.componentInstance.save();

    const req = httpMock.expectOne((r) => r.url.endsWith('/admin-key'));
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ key: 'sk-admin-secret-1234' });
    req.flush(SAVED);
    fixture.detectChanges();

    expect(changed).toBe(1);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('sk-…1234');
  });

  it('submits through the form element (ngSubmit fires) — not a native page reload', () => {
    // Regression: the <form> must carry [formGroup] or (ngSubmit) never binds — the submit
    // button then does a native page reload, save() never runs, and no PUT is sent (the DB
    // stayed empty and the page just reloaded). Driving the real form catches that; calling
    // save() directly (as other tests do) does not.
    const fixture = create(null);
    fixture.componentInstance.keyControl.setValue('sk-admin-secret-1234');
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement).querySelector('form')!.dispatchEvent(new Event('submit'));

    const req = httpMock.expectOne((r) => r.url.endsWith('/admin-key'));
    expect(req.request.method).toBe('PUT');
    req.flush(SAVED);
  });

  it('does not PUT a blank key', () => {
    const fixture = create(null);

    fixture.componentInstance.save();

    httpMock.expectNone((r) => r.method === 'PUT');
  });

  it('removes the key via DELETE, emits changed, and shows the form again', () => {
    const fixture = create(SAVED);
    let changed = 0;
    fixture.componentInstance.changed.subscribe(() => (changed += 1));

    fixture.componentInstance.remove();
    const req = httpMock.expectOne((r) => r.url.endsWith('/admin-key'));
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
    fixture.detectChanges();

    expect(changed).toBe(1);
    expect((fixture.nativeElement as HTMLElement).querySelector('input')).not.toBeNull();
  });

  it('rejects a project key client-side, without calling the API', () => {
    const fixture = create(null);

    fixture.componentInstance.keyControl.setValue('sk-proj-abc123def456');
    fixture.componentInstance.save();

    httpMock.expectNone((r) => r.url.endsWith('/admin-key') && r.method === 'PUT');
    expect(fixture.componentInstance.actionError()).toContain('sk-admin-');
  });

  it('surfaces the server message when an sk-admin- key is rejected by the server', () => {
    const fixture = create(null);

    fixture.componentInstance.keyControl.setValue('sk-admin-server-says-no');
    fixture.componentInstance.save();
    httpMock
      .expectOne((r) => r.url.endsWith('/admin-key'))
      .flush(
        { detail: 'The OpenAI admin key was rejected' },
        { status: 400, statusText: 'Bad Request' },
      );
    fixture.detectChanges();

    expect(fixture.componentInstance.actionError()).toContain('rejected');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('rejected');
  });
});
