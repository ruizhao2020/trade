import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { PublicApp } from './public/PublicApp.tsx'
import { setAppSurface } from './surface.ts'

setAppSurface('public')
createRoot(document.getElementById('root')!).render(<StrictMode><PublicApp /></StrictMode>)
