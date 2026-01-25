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
  if (auth.isAuthed && !auth.role) auth.logout()
  if (to.meta.public) {
    if (auth.isAuthed && to.path === '/login') return '/'
    return true
  }
  if (!auth.isAuthed) return { path: '/login', query: { redirect: to.fullPath } }
  const roles = to.meta.roles
  if (!roles) return true
  if (roles.includes(auth.role)) return true
  if (to.path !== '/') return '/'
  auth.logout()
  return { path: '/login' }
})

export default router
