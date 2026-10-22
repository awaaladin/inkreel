import '@fontsource-variable/fraunces';
import '@fontsource-variable/inter';
import './design/tokens.css';
import './design/global.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AppShell } from './components/AppShell';
import { StudioProvider } from './state';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <StudioProvider>
      <AppShell />
    </StudioProvider>
  </StrictMode>,
);
