import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/hosts',
  },
  {
    path: '/hosts',
    name: 'hosts',
    component: () => import('@/routes/HostsPage.vue'),
  },
  {
    path: '/scans',
    name: 'scans',
    component: () => import('@/routes/ScansPage.vue'),
  },
  {
    path: '/subscriptions',
    name: 'subscriptions',
    component: () => import('@/routes/SubscriptionsPage.vue'),
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/routes/SettingsPage.vue'),
  },
  {
    path: '/settings/params',
    name: 'params',
    component: () => import('@/routes/ParametersPage.vue'),
    meta: { hideNavbar: true },
  },
  {
    path: '/settings/orphans',
    name: 'orphans',
    component: () => import('@/routes/OrphanHostsPage.vue'),
    meta: { hideNavbar: true },
  },
  {
    path: '/logs',
    name: 'logs',
    component: () => import('@/routes/LogsPage.vue'),
    meta: { hideNavbar: true },
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
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }
    return { top: 0 }
  },
})

export default router
