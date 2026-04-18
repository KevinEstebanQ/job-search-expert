import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Nav from './components/Nav'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import Pipeline from './pages/Pipeline'
import CoverLetter from './pages/CoverLetter'
import Profile from './pages/Profile'

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/cover-letter/:jobId" element={<CoverLetter />} />
        <Route path="/profile" element={<Profile />} />
      </Routes>
    </BrowserRouter>
  )
}
