import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './store/auth'
import Layout from './components/Layout'
import Login from './pages/Login'

import { lazy, Suspense } from 'react'
const Dashboard     = lazy(() => import('./pages/Dashboard'))
const Subnets       = lazy(() => import('./pages/Subnets'))
const SubnetDetail  = lazy(() => import('./pages/SubnetDetail'))
const IpAddresses   = lazy(() => import('./pages/IpAddresses'))
const Vlans         = lazy(() => import('./pages/Vlans'))
const CapacityPlanner = lazy(() => import('./pages/CapacityPlanner'))
const DhcpLeases    = lazy(() => import('./pages/DhcpLeases'))
const DnsRecords    = lazy(() => import('./pages/DnsRecords'))
const Routes_       = lazy(() => import('./pages/Routes'))
const Conflicts     = lazy(() => import('./pages/Conflicts'))
const Alerts        = lazy(() => import('./pages/Alerts'))
const Logs          = lazy(() => import('./pages/Logs'))
const Settings      = lazy(() => import('./pages/Settings'))
const Documentation = lazy(() => import('./pages/Documentation'))

function PageFallback() {
  return <div className="flex items-center justify-center h-48 text-white">Loading…</div>
}

const isChromeless = new URLSearchParams(window.location.search).get('chromeless') === '1'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <PageFallback />
  if (!user) return <Navigate to="/login" replace />
  return <Layout chromeless={isChromeless}>{children}</Layout>
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <PageFallback />
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin') return <Navigate to="/" replace />
  return <Layout chromeless={isChromeless}>{children}</Layout>
}

// When loaded through pkthub's proxy, the browser's real path is
// /proxy/<app_id>/... — react-router needs that as its basename or every
// route fails to match and falls through to the "*" redirect (Dashboard).
const proxyPrefixMatch = window.location.pathname.match(/^\/proxy\/\d+/)
const routerBasename = proxyPrefixMatch ? proxyPrefixMatch[0] : undefined

export default function App() {
  return (
    <BrowserRouter basename={routerBasename}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><Dashboard /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/subnets" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><Subnets /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/subnets/:id" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><SubnetDetail /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/ip-addresses" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><IpAddresses /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/vlans" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><Vlans /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/capacity-planner" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><CapacityPlanner /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/sites" element={<Navigate to="/settings" replace />} />
          <Route path="/dhcp-leases" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><DhcpLeases /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/dns-records" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><DnsRecords /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/routes" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><Routes_ /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/conflicts" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><Conflicts /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/alerts" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><Alerts /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/logs" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><Logs /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/documentation" element={
            <ProtectedRoute>
              <Suspense fallback={<PageFallback />}><Documentation /></Suspense>
            </ProtectedRoute>
          } />
          <Route path="/collectors" element={<Navigate to="/settings" replace />} />
          <Route path="/integrations" element={<Navigate to="/settings" replace />} />
          <Route path="/settings" element={
            <AdminRoute>
              <Suspense fallback={<PageFallback />}><Settings /></Suspense>
            </AdminRoute>
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
