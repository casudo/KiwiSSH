<script setup lang="ts">
import { onMounted, computed, ref } from "vue"
import { useRouter } from "vue-router"
import { useDevicesStore } from "@/stores/devices"
import { useJobsStore } from "@/stores/jobs"
import { useAppStore } from "@/stores/app"
import { useFavoritesStore } from "@/stores/favorites"
import DeviceCard from "@/components/DeviceCard.vue"
import StatCard from "@/components/StatCard.vue"
import LoadingSpinner from "@/components/LoadingSpinner.vue"
import type { Device } from "@/types/device"

const router = useRouter()
const devicesStore = useDevicesStore()
const jobsStore = useJobsStore()
const appStore = useAppStore()
const favoritesStore = useFavoritesStore()
const configuredVendorCount = ref(0)
const configuredProfileCount = ref(0)

interface Stats {
  total: number
  enabled: number
  groups: number
  vendors: number
  sshProfiles: number
  backupJobs: number
}

const stats = computed((): Stats => ({
  total: devicesStore.deviceCount,
  enabled: devicesStore.enabledDevices.length,
  groups: Object.keys(devicesStore.devicesByGroup).length,
  vendors: configuredVendorCount.value || devicesStore.uniqueVendors.length,
  sshProfiles: configuredProfileCount.value || devicesStore.uniqueSshProfiles.length,
  backupJobs: jobsStore.totalJobs,
}))

const favoriteDevices = computed(() => {
  if (!favoritesStore.hasFavorites) {
    return []
  }

  // Filter devices that are in favorites list
  return devicesStore.devices.filter((device: Device) =>
    favoritesStore.isFavorite(device.device_name)
  )
})

const dashboardDevices = computed(() => favoriteDevices.value)

function goToDevice(deviceName: string) {
  router.push(`/devices/${deviceName}`)
}

onMounted(async () => {
  try {
    await favoritesStore.loadFavorites()
  } catch (e) {
    console.warn("Failed to load favorites from backend", e)
  }
  
  // Fetch configured vendor and SSH profile counts from API
  try {
    const [vendorsRes, profilesRes] = await Promise.all([
      fetch("/api/v1/vendors"),
      fetch("/api/v1/ssh-profiles"),
    ])
    
    if (vendorsRes.ok) {
      const vendorsData = await vendorsRes.json()
      configuredVendorCount.value = vendorsData.count || 0
    }
    
    if (profilesRes.ok) {
      const profilesData = await profilesRes.json()
      configuredProfileCount.value = profilesData.count || 0
    }
  } catch (e) {
    console.warn("Failed to fetch configured counts from API", e)
  }
  
  await Promise.all([
    devicesStore.fetchDevices(),
    devicesStore.fetchGroups(),
    devicesStore.fetchVendors(),
    jobsStore.loadJobs(),
    appStore.checkHealth(),
  ])
})
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-gray-100">Dashboard</h1>
      <p class="text-gray-500 dark:text-gray-400 mt-1">Overview of your network device backups</p>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-6 mb-8">
      <StatCard title="Total Devices" :value="stats.total" color="downtown" />
      <StatCard title="Enabled" :value="stats.enabled" color="green" />
      <StatCard title="Groups" :value="stats.groups" color="gray" />
      <StatCard title="Vendors" :value="stats.vendors" color="blue" />
      <StatCard title="SSH Profiles" :value="stats.sshProfiles" color="purple" />
      <StatCard title="Backup Job Log Lines" :value="stats.backupJobs" color="orange" />
    </div>

    <!-- Health Status -->
    <div v-if="appStore.health" class="card mb-8">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">System Status</h2>
          <p class="text-sm text-gray-500 dark:text-gray-400">API health check</p>
        </div>
        <div class="flex items-center space-x-2">
          <span
            class="w-3 h-3 rounded-full"
            :class="appStore.health.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'"
          ></span>
          <span class="font-medium capitalize">{{ appStore.health.status }}</span>
        </div>
      </div>
      <div class="mt-4 text-sm text-gray-500 dark:text-gray-400">
        Config loaded: {{ appStore.health.config_loaded ? "Yes" : "No" }}
      </div>
    </div>

    <!-- Favorite Devices -->
    <section>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Favorite Devices</h2>
        <RouterLink to="/devices" class="text-downtown-600 dark:text-downtown-400 hover:text-downtown-700 dark:hover:text-downtown-300 text-sm font-medium">
          View all →
        </RouterLink>
      </div>

      <LoadingSpinner v-if="devicesStore.loading" size="lg" class="py-12" />

      <div v-else-if="devicesStore.error" class="card text-center py-8">
        <p class="text-red-600">{{ devicesStore.error }}</p>
        <button @click="devicesStore.fetchDevices()" class="btn btn-primary mt-4">
          Retry
        </button>
      </div>

      <div v-else-if="devicesStore.devices.length === 0" class="card text-center py-12">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
        <p class="text-gray-500 dark:text-gray-400 text-lg">No devices configured yet</p>
        <p class="text-gray-400 dark:text-gray-500 text-sm mt-2">Add devices to your CSV source file to get started.</p>
      </div>

      <div v-else-if="favoriteDevices.length === 0" class="card text-center py-12">
        <p class="text-gray-500 dark:text-gray-400 text-lg">No favorites selected yet</p>
        <p class="text-gray-400 dark:text-gray-500 text-sm mt-2">Mark devices with the ☆ icon in the Devices view to pin them here.</p>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="device in dashboardDevices"
          :key="device.device_name"
          @click="goToDevice(device.device_name)"
        >
          <DeviceCard :device="device" />
        </div>
      </div>
    </section>
  </div>
</template>
