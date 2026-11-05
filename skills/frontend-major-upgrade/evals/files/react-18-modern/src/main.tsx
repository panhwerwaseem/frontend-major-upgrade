import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';

// Before React 18 this file called ReactDOM.render(<App />, container).
const container = document.getElementById('root') as HTMLElement;
createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>
);
