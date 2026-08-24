import { Bell, BookOpen, CalendarDays, ChartNoAxesCombined, ClipboardList, Gauge, History, LayoutDashboard, Settings, ShieldCheck, TriangleAlert, UserRoundCog, UsersRound } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { UserRole } from '../types/api'

export interface NavItem { label: string; path: string; icon: LucideIcon }

const common: NavItem[] = [
  { label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { label: 'Notifications', path: '/notifications', icon: Bell },
  { label: 'Account', path: '/account', icon: Settings },
]

export function navForRole(role: UserRole): NavItem[] {
  if (role === 'student') return [
    common[0],
    { label: 'My Timetable', path: '/timetable', icon: CalendarDays },
    { label: 'Enrollments', path: '/enrollments', icon: BookOpen },
    { label: 'Clash Reports', path: '/clash-reports', icon: TriangleAlert },
    common[1], common[2],
  ]
  if (role === 'faculty') return [
    common[0],
    { label: 'My Timetable', path: '/timetable', icon: CalendarDays },
    { label: 'Assignments', path: '/faculty-assignments', icon: ClipboardList },
    common[1], common[2],
  ]
  const operational: NavItem[] = [
    common[0],
    { label: 'Timetable', path: '/timetable', icon: CalendarDays },
    { label: 'Clash Management', path: '/clashes', icon: TriangleAlert },
    { label: 'Student Reports', path: '/clash-reports', icon: ClipboardList },
    { label: 'Faculty Assignments', path: '/faculty-assignments', icon: UsersRound },
    { label: 'Optimizer', path: '/optimizer', icon: ChartNoAxesCombined },
    { label: 'History', path: '/history', icon: History },
    common[1],
  ]
  if (role === 'admin') operational.splice(7, 0, { label: 'Users & Roles', path: '/admin/users', icon: UserRoundCog })
  operational.push(common[2])
  return operational
}

export const mobileStudentNav = [
  { label: 'Home', path: '/dashboard', icon: Gauge },
  { label: 'Timetable', path: '/timetable', icon: CalendarDays },
  { label: 'Reports', path: '/clash-reports', icon: TriangleAlert },
  { label: 'Notifications', path: '/notifications', icon: Bell },
  { label: 'More', path: '/account', icon: ShieldCheck },
]
