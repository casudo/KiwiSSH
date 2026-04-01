import { createRouter, createWebHistory } from "vue-router"
import type { RouteRecordRaw } from "vue-router"

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "dashboard",
    component: () => import("@/views/DashboardView.vue"),
    meta: { title: "Dashboard" }
  },
  {
    path: "/devices",
    name: "devices",
    component: () => import("@/views/DevicesView.vue"),
    meta: { title: "Devices" }
  },
  {
    path: "/devices/:name",
    name: "device-detail",
    component: () => import("@/views/DeviceDetailView.vue"),
    meta: { title: "Device Detail" }
  },
  {
    path: "/vendors",
    name: "vendors",
    component: () => import("@/views/VendorsView.vue"),
    meta: { title: "Vendors" }
  },
  {
    path: "/groups",
    name: "groups",
    component: () => import("@/views/GroupsView.vue"),
    meta: { title: "Groups" }
  },
  {
    path: "/ssh-profiles",
    name: "ssh-profiles",
    component: () => import("@/views/SshProfilesView.vue"),
    meta: { title: "SSH Profiles" }
  },
  {
    path: "/jobs",
    name: "jobs",
    component: () => import("@/views/JobsView.vue"),
    meta: { title: "Backup Jobs" }
  },
  {
    path: "/settings",
    name: "settings",
    component: () => import("@/views/SettingsView.vue"),
    meta: { title: "Settings" }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Update document title on route change
router.beforeEach((to, from, next) => {
  const title = to.meta.title as string || "Page"
  document.title = `${title} | KiwiSSH`
  next()
})

export default router
