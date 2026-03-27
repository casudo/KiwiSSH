<script setup lang="ts">
import { onMounted, computed, ref } from "vue"
import { useDevicesStore } from "@/stores/devices"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

const devicesStore = useDevicesStore()
const selectedProfile = ref<string | null>(null)

interface SSHProfileInfo {
  name: string
  count: number
  devices: string[]
}

const sshProfileList = computed((): SSHProfileInfo[] => {
  const profiles: Record<string, string[]> = {}

  devicesStore.devices.forEach(device => {
    if (!profiles[device.ssh_profile]) {
      profiles[device.ssh_profile] = []
    }
    profiles[device.ssh_profile].push(device.device_name)
  })

  return Object.entries(profiles)
    .map(([name, devices]) => ({
      name,
      count: devices.length,
      devices,
    }))
    .sort((a, b) => a.name.localeCompare(b.name))
})

onMounted(async () => {
  if (devicesStore.devices.length === 0) {
    await Promise.all([
      devicesStore.fetchDevices(),
      devicesStore.fetchGroups(),
    ])
  }
})
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900">SSH Profiles</h1>
      <p class="text-gray-500 mt-1">SSH connection profiles and assigned devices</p>
    </div>

    <LoadingSpinner v-if="devicesStore.loading" size="lg" class="py-12" />

    <div v-else-if="sshProfileList.length === 0" class="card text-center py-12">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
      <p class="text-gray-500 text-lg">No SSH profiles configured</p>
      <p class="text-gray-400 text-sm mt-2">Add devices to see SSH profiles</p>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="profile in sshProfileList"
        :key="profile.name"
        @click="selectedProfile = profile.name"
        class="card-hover cursor-pointer"
      >
        <div class="flex items-start justify-between mb-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-900 capitalize">{{ profile.name }}</h3>
            <p class="text-sm text-gray-500 mt-1">{{ profile.count }} {{ profile.count === 1 ? "device" : "devices" }}</p>
          </div>
          <span class="inline-flex items-center justify-center h-12 w-12 rounded-lg bg-purple-100">
            <span class="text-lg font-semibold text-purple-600">{{ profile.count }}</span>
          </span>
        </div>

        <div class="mt-4">
          <p class="text-xs text-gray-500 font-medium mb-2">Used by:</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="device in profile.devices.slice(0, 3)"
              :key="device"
              class="inline-block px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded"
            >
              {{ device }}
            </span>
            <span
              v-if="profile.devices.length > 3"
              class="inline-block px-2 py-1 text-gray-600 text-xs"
            >
              +{{ profile.devices.length - 3 }} more
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail panel -->
    <div v-if="selectedProfile" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div class="bg-white rounded-lg shadow-xl max-w-md w-full max-h-screen overflow-y-auto">
        <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-gray-900 capitalize">{{ selectedProfile }}</h2>
          <button
            @click="selectedProfile = null"
            class="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        <div class="px-6 py-4">
          <div class="mb-6">
            <h3 class="text-sm font-medium text-gray-900 mb-2">Configuration</h3>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-600">Profile Name:</span>
                <span class="font-medium text-gray-900 capitalize">{{ selectedProfile }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">Total Devices:</span>
                <span class="font-medium text-gray-900">
                  {{ devicesStore.devices.filter(d => d.ssh_profile === selectedProfile).length }}
                </span>
              </div>
              <p class="text-xs text-gray-500 mt-2">Configured in config/ssh_profiles.yaml</p>
            </div>
          </div>

          <div>
            <h3 class="text-sm font-medium text-gray-900 mb-2">Devices Using This Profile</h3>
            <div class="space-y-2">
              <div
                v-for="device in devicesStore.devices.filter(d => d.ssh_profile === selectedProfile)"
                :key="device.device_name"
                class="p-3 bg-gray-50 rounded text-sm"
              >
                <p class="font-medium text-gray-900">{{ device.device_name }}</p>
                <p class="text-gray-500 text-xs">{{ device.ip_address }} ({{ device.vendor }})</p>
              </div>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  </div>
</template>
