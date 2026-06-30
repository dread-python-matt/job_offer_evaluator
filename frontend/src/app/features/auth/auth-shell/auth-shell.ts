import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * Shared chrome for every auth screen: the page's `<mat-card>` (supplied via
 * content projection) centered on a soft branded backdrop. Keeps the layout,
 * backdrop, and centering in one place so each auth feature only owns its form.
 */
@Component({
  selector: 'app-auth-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './auth-shell.html',
  styleUrl: './auth-shell.scss',
})
export class AuthShell {}
