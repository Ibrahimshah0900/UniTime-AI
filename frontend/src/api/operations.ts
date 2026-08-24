import { apiRequest, queryString } from './client'
import type {
  AuditTrail,
  ClashCollection,
  GlobalOptimization,
  OptimizerExecution,
  OptimizerExecutionCollection,
  OptimizerPlan,
  RoomSuggestionCollection,
  StudentGroupCollection,
  StudentResolutionCollection,
  StudentRiskCollection,
  StudentScheduleChangeCollection,
  TimetableChangeCollection,
} from '../types/operations'

export const clashesApi = {
  all: () => apiRequest<ClashCollection>('/clashes'),
  roomSuggestions: () => apiRequest<RoomSuggestionCollection>('/clashes/room-suggestions'),
  studentRisk: () => apiRequest<StudentRiskCollection>('/clashes/student-risk'),
  studentGroups: () => apiRequest<StudentGroupCollection>('/clashes/student-groups'),
  studentResolutions: () => apiRequest<StudentResolutionCollection>('/clashes/student-resolutions'),
  applyRoomFix: (entry1: number, entry2: number) => apiRequest<unknown>(`/clashes/room/${entry1}/${entry2}/apply-best-fix`, { method: 'POST' }),
  applyStudentGroupFix: (groupId: number) => apiRequest<unknown>(`/clashes/student-groups/${groupId}/apply-best-fix`, { method: 'POST' }),
}

export const optimizerApi = {
  global: (limit = 20) => apiRequest<GlobalOptimization>(`/optimizer/global${queryString({ limit })}`),
  applyGlobalBest: () => apiRequest<unknown>('/optimizer/global/apply-best', { method: 'POST' }),
  plan: (maxSteps = 5) => apiRequest<OptimizerPlan>(`/optimizer/plan${queryString({ max_steps: maxSteps })}`),
  applyPlan: (maxSteps = 5) => apiRequest<unknown>(`/optimizer/plan/apply${queryString({ max_steps: maxSteps })}`, { method: 'POST' }),
  executions: () => apiRequest<OptimizerExecutionCollection>('/optimizer/executions'),
  execution: (id: string) => apiRequest<OptimizerExecution>(`/optimizer/executions/${id}`),
  undoExecution: (id: string) => apiRequest<unknown>(`/optimizer/executions/${id}/undo`, { method: 'POST' }),
  redoExecution: (id: string) => apiRequest<unknown>(`/optimizer/executions/${id}/redo`, { method: 'POST' }),
}

export const historyApi = {
  changes: () => apiRequest<TimetableChangeCollection>('/changes'),
  undoChange: (id: number) => apiRequest<unknown>(`/changes/${id}/undo`, { method: 'POST' }),
  redoChange: (id: number) => apiRequest<unknown>(`/changes/${id}/redo`, { method: 'POST' }),
  studentChanges: () => apiRequest<StudentScheduleChangeCollection>('/student-schedule-changes'),
  undoStudentChange: (id: number) => apiRequest<unknown>(`/student-schedule-changes/${id}/undo`, { method: 'POST' }),
  redoStudentChange: (id: number) => apiRequest<unknown>(`/student-schedule-changes/${id}/redo`, { method: 'POST' }),
  audit: () => apiRequest<AuditTrail>('/audit-trail'),
}
