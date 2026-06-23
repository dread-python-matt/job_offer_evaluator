import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormArray, FormBuilder, FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { TextFieldModule } from '@angular/cdk/text-field';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule, MatChipInputEvent } from '@angular/material/chips';
import { MAT_DATE_FORMATS, MatDateFormats, provideNativeDateAdapter } from '@angular/material/core';
import { MatDatepicker, MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { catchError, of } from 'rxjs';

import { ApiService } from '../../core/services/api.service';
import { Experience, Project, Skill, UserProfile } from '../../core/models/profile.model';

const MONTH_YEAR_FORMATS: MatDateFormats = {
  parse: {
    dateInput: { year: 'numeric', month: 'short' },
  },
  display: {
    dateInput: { year: 'numeric', month: 'short' },
    monthYearLabel: { year: 'numeric', month: 'short' },
    dateA11yLabel: { year: 'numeric', month: 'long' },
    monthYearA11yLabel: { year: 'numeric', month: 'long' },
  },
};

interface SkillControls {
  name: FormControl<string>;
  rating: FormControl<number>;
}

interface ProjectControls {
  name: FormControl<string>;
  repository_link: FormControl<string>;
  summary: FormControl<string>;
  date_from: FormControl<Date | null>;
  date_to: FormControl<Date | null>;
  date_to_present: FormControl<boolean>;
  tech_stack: FormControl<string[]>;
}

interface ExperienceControls {
  title: FormControl<string>;
  company: FormControl<string>;
  description: FormControl<string>;
  date_from: FormControl<Date | null>;
  date_to: FormControl<Date | null>;
  date_to_present: FormControl<boolean>;
  tech_stack: FormControl<string[]>;
}

type SkillGroup = FormGroup<SkillControls>;
type ProjectGroup = FormGroup<ProjectControls>;
type ExperienceGroup = FormGroup<ExperienceControls>;

type ProjectRaw = ReturnType<ProjectGroup['getRawValue']>;
type ExperienceRaw = ReturnType<ExperienceGroup['getRawValue']>;

@Component({
  selector: 'app-profile',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    provideNativeDateAdapter(),
    { provide: MAT_DATE_FORMATS, useValue: MONTH_YEAR_FORMATS },
  ],
  imports: [
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatChipsModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatTooltipModule,
    TextFieldModule,
  ],
  templateUrl: './profile.html',
  styleUrl: './profile.scss',
})
export class Profile implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  readonly saving = signal(false);
  readonly mode = signal<'view' | 'edit'>('edit');
  readonly profileData = signal<UserProfile | null>(null);

  readonly form = this.fb.group({
    summary: this.fb.control('', { nonNullable: true, validators: Validators.required }),
    skills: this.fb.array<SkillGroup>([]),
    projects: this.fb.array<ProjectGroup>([]),
    experience: this.fb.array<ExperienceGroup>([]),
  });

  get skills(): FormArray<SkillGroup> {
    return this.form.controls.skills;
  }

  get projects(): FormArray<ProjectGroup> {
    return this.form.controls.projects;
  }

  get experience(): FormArray<ExperienceGroup> {
    return this.form.controls.experience;
  }

  ngOnInit(): void {
    this.api
      .getProfile()
      .pipe(catchError(() => of(null)))
      .subscribe((profile) => {
        this.profileData.set(profile);
        this.populateForm(profile);
        this.mode.set(profile ? 'view' : 'edit');
      });
  }

  edit(): void {
    this.mode.set('edit');
  }

  cancel(): void {
    const saved = this.profileData();
    if (!saved) return;
    this.populateForm(saved);
    this.mode.set('view');
  }

  addSkill(): void {
    this.skills.push(this.buildSkillGroup());
  }

  removeSkill(index: number): void {
    const removed = this.skills.at(index).getRawValue();
    this.skills.removeAt(index);
    this.offerUndo('Skill removed.', () => this.skills.insert(index, this.buildSkillGroup(removed)));
  }

  setSkillRating(index: number, rating: number): void {
    const control = this.skills.at(index).controls.rating;
    control.setValue(rating);
    control.markAsTouched();
  }

  addProject(): void {
    this.projects.push(this.buildProjectGroup());
  }

  removeProject(index: number): void {
    const removed = this.toProject(this.projects.at(index).getRawValue());
    this.projects.removeAt(index);
    this.offerUndo('Project removed.', () =>
      this.projects.insert(index, this.buildProjectGroup(removed)),
    );
  }

  addExperience(): void {
    this.experience.push(this.buildExperienceGroup());
  }

  removeExperience(index: number): void {
    const removed = this.toExperience(this.experience.at(index).getRawValue());
    this.experience.removeAt(index);
    this.offerUndo('Experience removed.', () =>
      this.experience.insert(index, this.buildExperienceGroup(removed)),
    );
  }

  onProjectPresentChange(index: number, checked: boolean): void {
    const ctrl = this.projects.at(index).controls.date_to;
    checked ? ctrl.disable() : ctrl.enable();
  }

  onExperiencePresentChange(index: number, checked: boolean): void {
    const ctrl = this.experience.at(index).controls.date_to;
    checked ? ctrl.disable() : ctrl.enable();
  }

  onProjectFromMonth(index: number, date: Date, picker: MatDatepicker<Date>): void {
    this.projects.at(index).controls.date_from.setValue(this.firstOfMonth(date));
    picker.close();
  }

  onProjectToMonth(index: number, date: Date, picker: MatDatepicker<Date>): void {
    this.projects.at(index).controls.date_to.setValue(this.firstOfMonth(date));
    picker.close();
  }

  onExperienceFromMonth(index: number, date: Date, picker: MatDatepicker<Date>): void {
    this.experience.at(index).controls.date_from.setValue(this.firstOfMonth(date));
    picker.close();
  }

  onExperienceToMonth(index: number, date: Date, picker: MatDatepicker<Date>): void {
    this.experience.at(index).controls.date_to.setValue(this.firstOfMonth(date));
    picker.close();
  }

  formatDate(dateStr: string): string {
    if (!dateStr || dateStr === 'Present') return dateStr;
    const [yearStr, monthStr] = dateStr.split('-');
    if (!yearStr || !monthStr) return dateStr;
    const date = new Date(Number(yearStr), Number(monthStr) - 1);
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
  }

  private firstOfMonth(date: Date): Date {
    return new Date(date.getFullYear(), date.getMonth(), 1);
  }

  private parseYearMonth(str: string | undefined | null): Date | null {
    if (!str || str === 'Present') return null;
    const [yearStr, monthStr] = str.split('-');
    if (!yearStr || !monthStr) return null;
    return new Date(Number(yearStr), Number(monthStr) - 1, 1);
  }

  private formatYearMonth(date: Date | null): string {
    if (!date) return '';
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
  }

  private offerUndo(message: string, undo: () => void): void {
    const ref = this.snackBar.open(message, 'Undo', { duration: 5000 });
    ref.onAction().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(undo);
  }

  private toProject(raw: ProjectRaw): Project {
    return {
      name: raw.name,
      repository_link: raw.repository_link,
      summary: raw.summary,
      date_from: this.formatYearMonth(raw.date_from),
      date_to: raw.date_to_present ? 'Present' : this.formatYearMonth(raw.date_to),
      tech_stack: [...raw.tech_stack],
    };
  }

  private toExperience(raw: ExperienceRaw): Experience {
    return {
      title: raw.title,
      company: raw.company,
      description: raw.description,
      date_from: this.formatYearMonth(raw.date_from),
      date_to: raw.date_to_present ? 'Present' : this.formatYearMonth(raw.date_to),
      tech_stack: [...raw.tech_stack],
    };
  }

  addProjectTech(index: number, event: MatChipInputEvent): void {
    this.addTech(this.projects.at(index).controls.tech_stack, event);
  }

  removeProjectTech(index: number, tech: string): void {
    this.removeTech(this.projects.at(index).controls.tech_stack, tech);
  }

  addExperienceTech(index: number, event: MatChipInputEvent): void {
    this.addTech(this.experience.at(index).controls.tech_stack, event);
  }

  removeExperienceTech(index: number, tech: string): void {
    this.removeTech(this.experience.at(index).controls.tech_stack, tech);
  }

  private addTech(control: FormControl<string[]>, event: MatChipInputEvent): void {
    const existing = new Set(control.value);
    const toAdd = event.value
      .split(',')
      .map((v) => v.trim())
      .filter((v) => v && !existing.has(v));
    if (toAdd.length) {
      control.setValue([...control.value, ...toAdd]);
    }
    event.chipInput.clear();
  }

  private removeTech(control: FormControl<string[]>, tech: string): void {
    control.setValue(control.value.filter((item) => item !== tech));
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.snackBar.open('Fix the highlighted fields before saving.', 'Dismiss', { duration: 4000 });
      return;
    }

    const value = this.form.getRawValue();
    const profile: UserProfile = {
      summary: value.summary,
      skills: value.skills.map((skill) => ({ name: skill.name, rating: Number(skill.rating) })),
      projects: value.projects.map((p) => this.toProject(p)),
      experience: value.experience.map((e) => this.toExperience(e)),
    };

    this.saving.set(true);
    this.api.saveProfile(profile).subscribe({
      next: () => {
        this.saving.set(false);
        this.profileData.set(profile);
        this.mode.set('view');
        this.snackBar.open('Profile saved.', 'Dismiss', { duration: 3000 });
      },
      error: () => {
        this.saving.set(false);
        this.snackBar.open('Failed to save profile.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  private populateForm(profile: UserProfile | null): void {
    this.form.patchValue({ summary: profile?.summary ?? '' });

    this.skills.clear();
    (profile?.skills ?? []).forEach((skill) => this.skills.push(this.buildSkillGroup(skill)));

    this.projects.clear();
    (profile?.projects ?? []).forEach((project) => this.projects.push(this.buildProjectGroup(project)));

    this.experience.clear();
    (profile?.experience ?? []).forEach((exp) => this.experience.push(this.buildExperienceGroup(exp)));
  }

  private buildSkillGroup(skill?: Skill): SkillGroup {
    return this.fb.group({
      name: this.fb.control(skill?.name ?? '', { nonNullable: true, validators: Validators.required }),
      rating: this.fb.control(skill?.rating ?? 3, {
        nonNullable: true,
        validators: [Validators.required, Validators.min(1), Validators.max(5)],
      }),
    });
  }

  private buildProjectGroup(project?: Project): ProjectGroup {
    const isPresent = project?.date_to === 'Present';
    const group = this.fb.group({
      name: this.fb.control(project?.name ?? '', { nonNullable: true, validators: Validators.required }),
      repository_link: this.fb.control(project?.repository_link ?? '', { nonNullable: true }),
      summary: this.fb.control(project?.summary ?? '', {
        nonNullable: true,
        validators: Validators.required,
      }),
      date_from: this.fb.control<Date | null>(this.parseYearMonth(project?.date_from), {
        validators: Validators.required,
      }),
      date_to: this.fb.control<Date | null>(this.parseYearMonth(isPresent ? null : project?.date_to)),
      date_to_present: this.fb.control(isPresent, { nonNullable: true }),
      tech_stack: this.fb.control(project?.tech_stack ?? [], { nonNullable: true }),
    });
    if (isPresent) group.controls.date_to.disable();
    return group;
  }

  private buildExperienceGroup(exp?: Experience): ExperienceGroup {
    const isPresent = exp?.date_to === 'Present';
    const group = this.fb.group({
      title: this.fb.control(exp?.title ?? '', { nonNullable: true, validators: Validators.required }),
      company: this.fb.control(exp?.company ?? '', {
        nonNullable: true,
        validators: Validators.required,
      }),
      description: this.fb.control(exp?.description ?? '', {
        nonNullable: true,
        validators: Validators.required,
      }),
      date_from: this.fb.control<Date | null>(this.parseYearMonth(exp?.date_from), {
        validators: Validators.required,
      }),
      date_to: this.fb.control<Date | null>(this.parseYearMonth(isPresent ? null : exp?.date_to)),
      date_to_present: this.fb.control(isPresent, { nonNullable: true }),
      tech_stack: this.fb.control(exp?.tech_stack ?? [], { nonNullable: true }),
    });
    if (isPresent) group.controls.date_to.disable();
    return group;
  }
}
