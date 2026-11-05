import { Component } from '@angular/core';
import { MatLegacyDialog as MatDialog } from '@angular/material/legacy-dialog';

import { ConfirmDialogComponent } from './confirm-dialog.component';

@Component({
  selector: 'app-root',
  template: `
    <mat-toolbar>Claims</mat-toolbar>
    <button mat-raised-button (click)="confirm()">Close claim</button>
  `,
})
export class AppComponent {
  constructor(private readonly dialog: MatDialog) {}

  confirm(): void {
    this.dialog.open(ConfirmDialogComponent, { data: { claimId: 'C-1042' } });
  }
}
