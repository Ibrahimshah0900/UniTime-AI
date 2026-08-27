import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MotionConfig } from 'motion/react'
import App from './app/App'
import { AuthProvider } from './features/auth/AuthContext'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <AuthProvider>
          <App/>
        </AuthProvider>
      </BrowserRouter>
    </MotionConfig>
  </StrictMode>,
)
