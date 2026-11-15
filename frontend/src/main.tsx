import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import { AuthProvider } from './AuthProvider.tsx'
import './index.css'

// dark mode chosen before (Sidebar button) also applies to the login screen
try {
  if (localStorage.getItem('openrec_theme') === 'dark') document.documentElement.dataset.theme = 'dark'
} catch {
  /* private window */
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)