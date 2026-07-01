import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/hosts',
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/routes/LoginPage.vue'),
    meta: { public: true },
  },
  {
    path: '/hosts',
    name: 'hosts',
    component: () => import('@/routes/HostsPage.vue'),
  },
  {
    path: '/scan',
    name: 'scan',
    component: () => import('@/routes/ScanPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/subscriptions',
    name: 'subscriptions',
    component: () => import('@/routes/SubscriptionsPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/routes/SettingsPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings/params',
    name: 'params',
    component: () => import('@/routes/ParametersPage.vue'),
    meta: { requiresAuth: true, hideNavbar: true },
  },
  {
    path: '/settings/orphans',
    name: 'orphans',
    component: () => import('@/routes/OrphanHostsPage.vue'),
    meta: { requiresAuth: true, hideNavbar: true },
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/routes/LogsPage.vue'),
    meta: { requiresAuth: true, hideNavbar: true },
  },
  {
    path: '/:pathMatch(.*)*',
    component: () => import('@/routes/NotFound.vue'),
    meta: { hideNavbar: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：未登录时跳转到登录页（仅 meta.public 的路由可匿名访问）
router.beforeEach((to) => {
  if (to.meta.public) return true

  const token = localStorage.getItem('auth_token')
  if (!token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
