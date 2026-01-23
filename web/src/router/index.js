import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', component: () => import('../views/Login.vue'), meta: { public: true } },
  { path: '/', component: () => import('../views/UserList.vue'), meta: { roles: ['admin', 'operator', 'viewer'] } },
  { path: '/audit', component: () => import('../views/AuditLogs.vue'), meta: { roles: ['admin'] } },
  { path: '/admins', component: () => import('../views/AdminUsers.vue'), meta: { roles: ['admin'] } },
  { path: '/create', component: () => import('../views/UserEdit.vue'), meta: { roles: ['admin', 'operator'] } },
  { path: '/edit/:id', component: () => import('../views/UserEdit.vue'), meta: { roles: ['admin', 'operator'] } }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta?.public) return true
  const auth = useAuthStore()
  if (!auth.isAuthed) return { path: '/login', replace: true }
  const roles = to.meta?.roles
  if (Array.isArray(roles) && roles.length) {
    if (!roles.includes(auth.role)) return { path: '/', replace: true }
  }
  return true
})

export default router
