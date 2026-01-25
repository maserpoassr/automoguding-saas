import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', component: () => import('../views/Login.vue'), meta: { public: true } },
  { path: '/', component: () => import('../views/UserList.vue'), meta: { roles: ['admin', 'operator', 'viewer'] } },
  { path: '/audit', component: () => import('../views/AuditLogs.vue'), meta: { roles: ['admin'] } },
  { path: '/create', component: () => import('../views/UserEdit.vue'), meta: { roles: ['admin', 'operator'] } },
  { path: '/edit/:id', component: () => import('../views/UserEdit.vue'), meta: { roles: ['admin', 'operator'] } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.isAuthed) return '/login'
  const roles = to.meta.roles
  if (!roles) return true
  if (roles.includes(auth.role)) return true
  return '/'
})

export default router
