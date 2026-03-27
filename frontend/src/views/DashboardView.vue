<script setup lang="ts">
import { onMounted, computed } from "vue"
import { useRouter } from "vue-router"
import { useDevicesStore } from "@/stores/devices"
import { useAppStore } from "@/stores/app"
import DeviceCard from "@/components/DeviceCard.vue"
import StatCard from "@/components/StatCard.vue"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

const router = useRouter()
const devicesStore = useDevicesStore()
const appStore = useAppStore()

interface Stats {
  total: number
  enabled: number
  groups: number
  vendors: number
  sshProfiles: number
}

const stats = computed((): Stats => ({
  total: devicesStore.deviceCount,
  enabled: devicesStore.enabledDevices.length,
  groups: Object.keys(devicesStore.devicesByGroup).length,
  vendors: devicesStore.uniqueVendors.length,
  sshProfiles: devicesStore.uniqueSshProfiles.length,
}))

const recentDevices = computed(() => {
  return devicesStore.devices.slice(0, 6)
})

function goToDevice(deviceName: string) {
  router.push(`/devices/${deviceName}`)
}

onMounted(async () => {
  await Promise.all([
    devicesStore.fetchDevices(),
    devicesStore.fetchGroups(),
    appStore.checkHealth(),
  ])
})
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900">Dashboard</h1>
      <p class="text-gray-500 mt-1">Overview of your network device backups</p>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6 mb-8">
      <StatCard title="Total Devices" :value="stats.total" color="downtown" />
      <StatCard title="Enabled" :value="stats.enabled" color="green" />
      <StatCard title="Groups" :value="stats.groups" color="gray" />
      <StatCard title="Vendors" :value="stats.vendors" color="blue" />
      <StatCard title="SSH Profiles" :value="stats.sshProfiles" color="purple" />
    </div>

    <!-- Health Status -->
    <div v-if="appStore.health" class="card mb-8">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-lg font-semibold text-gray-900">System Status</h2>
          <p class="text-sm text-gray-500">API health check</p>
        </div>
        <div class="flex items-center space-x-2">
          <span
            class="w-3 h-3 rounded-full"
            :class="appStore.health.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'"
          ></span>
          <span class="font-medium capitalize">{{ appStore.health.status }}</span>
        </div>
      </div>
      <div class="mt-4 text-sm text-gray-500">
        Config loaded: {{ appStore.health.config_loaded ? "Yes" : "No" }}
      </div>
    </div>

    <!-- Recent Devices -->
    <section>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xl font-semibold text-gray-900">Devices</h2>
        <RouterLink to="/devices" class="text-downtown-600 hover:text-downtown-700 text-sm font-medium">
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
        <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
        <p class="text-gray-500 text-lg">No devices configured yet</p>
        <p class="text-gray-400 text-sm mt-2">Add devices to your CSV source file to get started.</p>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="device in recentDevices"
          :key="device.device_name"
          @click="goToDevice(device.device_name)"
        >
          <DeviceCard :device="device" />
        </div>
      </div>
    </section>
  </div>
</template>
