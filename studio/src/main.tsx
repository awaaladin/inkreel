import '@fontsource-variable/inter';
import './styles.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './components/App';
import { StudioProvider } from './state';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <StudioProvider>
      <App />
    </StudioProvider>
  </StrictMode>,
);
