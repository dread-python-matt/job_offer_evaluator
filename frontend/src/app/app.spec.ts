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
    // The name is a two-tone wordmark: "Job Offer" (lead) + "Matcher" (accent).
    const norm = (sel: string) =>
      brand?.querySelector(sel)?.textContent?.replace(/\s+/g, ' ').trim();
    expect(norm('.brand-name-lead')).toBe('Job Offer');
    expect(norm('.brand-name-accent')).toBe('Matcher');
  });
});
