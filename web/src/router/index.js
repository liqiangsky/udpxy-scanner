import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/hosts',
  },
  {
    path: '/login',
    component: () => import('@/routes/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/hosts',
    component: () => import('@/routes/HostList.vue'),
  },
  {
    path: '/configs',
    component: () => import('@/routes/ScanConfig.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/sources',
    component: () => import('@/routes/DataSources.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings',
    component: () => import('@/routes/GlobalSettings.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/logs',
    component: () => import('@/routes/ServerLogs.vue'),
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
