import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * The Merge brand badge — the same "merge node" glyph the app toolbar uses, in a
 * rounded accent tile. Size is driven by the `--auth-logo-size` custom property
 * (default 40px) so a host can scale it without an input.
 */
@Component({
  selector: 'app-auth-logo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './auth-logo.html',
  styleUrl: './auth-logo.scss',
})
export class AuthLogo {}
