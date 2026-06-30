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

  it('shows the masked hint when an admin key is already saved', () => {
    const fixture = create(SAVED);

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('sk-…1234');
    expect(el.querySelector('input')).toBeNull();
  });

  it('shows the add form when no admin key is saved', () => {
    const fixture = create(null);

    expect((fixture.nativeElement as HTMLElement).querySelector('input')).not.toBeNull();
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

  it('surfaces the server message when saving is rejected', () => {
    const fixture = create(null);

    fixture.componentInstance.keyControl.setValue('sk-bad');
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
