import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { MatLegacyButtonModule } from '@angular/material/legacy-button';
import { MatLegacyDialogModule } from '@angular/material/legacy-dialog';
import { MatToolbarModule } from '@angular/material/toolbar';

import { AppComponent } from './app.component';
import { ConfirmDialogComponent } from './confirm-dialog.component';

@NgModule({
  declarations: [AppComponent, ConfirmDialogComponent],
  imports: [
    BrowserModule,
    BrowserAnimationsModule,
    MatLegacyButtonModule,
    MatLegacyDialogModule,
    MatToolbarModule,
  ],
  entryComponents: [ConfirmDialogComponent],
  bootstrap: [AppComponent],
})
export class AppModule {}
