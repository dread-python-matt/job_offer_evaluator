import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('renders the brand wordmark as a home link', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    const brand = compiled.querySelector('mat-toolbar a.brand');
    expect(brand?.getAttribute('href')).toBe('/profile');
    // The wordmark is "Merge" with an accent "merge node" dot.
    expect(brand?.querySelector('.brand-word')?.textContent?.trim()).toBe('Merge');
    expect(brand?.querySelector('.brand-dot')?.textContent?.trim()).toBe('.');
    expect(brand?.querySelector('.brand-tagline')?.textContent?.trim()).toBe(
      'your skills with the right role',
    );
  });
});
