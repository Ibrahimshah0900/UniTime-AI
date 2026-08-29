import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '../layouts/AppShell'
import { ProtectedRoute } from '../routes/ProtectedRoute'
import { AccountPage } from '../pages/AccountPage'
import { AdminUsersPage } from '../pages/AdminUsersPage'
import { LoginPage, RegisterPage, ForbiddenPage } from '../pages/AuthPages'
import { ClashReportsPage } from '../pages/ClashReportsPage'
import { DashboardPage } from '../pages/DashboardPage'
import { EnrollmentsPage } from '../pages/EnrollmentsPage'
import { FacultyAssignmentsPage } from '../pages/FacultyAssignmentsPage'
import { NotificationsPage } from '../pages/NotificationsPage'
import { ClashesPage, HistoryPage, OptimizerPage } from '../pages/OperationsPages'
import { TimetablePage } from '../pages/TimetablePage'
import { InsightsPage } from '../pages/InsightsPage'
import { AcademicTermsPage } from '../pages/AcademicTermsPage'
import { InstitutionalSchedulingPage } from '../pages/InstitutionalSchedulingPage'
import { FacultyAvailabilityPage } from '../pages/FacultyAvailabilityPage'
import { StudentsPage } from '../pages/StudentsPage'

export default function App() {
  return <Routes>
    <Route path="/login" element={<LoginPage/>}/>
    <Route path="/register" element={<RegisterPage/>}/>
    <Route path="/forbidden" element={<ForbiddenPage/>}/>
    <Route element={<ProtectedRoute><AppShell/></ProtectedRoute>}>
      <Route index element={<Navigate to="/dashboard" replace/>}/>
      <Route path="dashboard" element={<DashboardPage/>}/>
      <Route path="timetable" element={<TimetablePage/>}/>
      <Route path="academic-terms" element={<ProtectedRoute roles={['coordinator','admin']}><AcademicTermsPage/></ProtectedRoute>}/>
      <Route path="students" element={<ProtectedRoute roles={['coordinator','admin']}><StudentsPage/></ProtectedRoute>}/>
      <Route path="scheduling" element={<ProtectedRoute roles={['coordinator','admin']}><InstitutionalSchedulingPage/></ProtectedRoute>}/>
      <Route path="faculty-availability" element={<ProtectedRoute roles={['faculty']}><FacultyAvailabilityPage/></ProtectedRoute>}/>
      <Route path="notifications" element={<NotificationsPage/>}/>
      <Route path="account" element={<AccountPage/>}/>
      <Route path="enrollments" element={<ProtectedRoute roles={['student']}><EnrollmentsPage/></ProtectedRoute>}/>
      <Route path="clash-reports" element={<ProtectedRoute roles={['student','coordinator','admin']}><ClashReportsPage/></ProtectedRoute>}/>
      <Route path="faculty-assignments" element={<ProtectedRoute roles={['faculty','coordinator','admin']}><FacultyAssignmentsPage/></ProtectedRoute>}/>
      <Route path="clashes" element={<ProtectedRoute roles={['coordinator','admin']}><ClashesPage/></ProtectedRoute>}/>
      <Route path="optimizer" element={<ProtectedRoute roles={['coordinator','admin']}><OptimizerPage/></ProtectedRoute>}/>
      <Route path="history" element={<ProtectedRoute roles={['coordinator','admin']}><HistoryPage/></ProtectedRoute>}/>
      <Route path="insights" element={<ProtectedRoute roles={['coordinator','admin']}><InsightsPage/></ProtectedRoute>}/>
      <Route path="admin/users" element={<ProtectedRoute roles={['admin']}><AdminUsersPage/></ProtectedRoute>}/>
    </Route>
    <Route path="*" element={<Navigate to="/dashboard" replace/>}/>
  </Routes>
}
