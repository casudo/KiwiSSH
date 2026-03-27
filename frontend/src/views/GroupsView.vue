<script setup lang="ts">
import { onMounted, computed, ref } from "vue"
import { useDevicesStore } from "@/stores/devices"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

const devicesStore = useDevicesStore()
const selectedGroup = ref<string | null>(null)

interface GroupInfo {
  name: string
  count: number
  devices: string[]
}

const groupList = computed((): GroupInfo[] => {
  return devicesStore.groups.map(group => ({
    name: group,
    count: (devicesStore.devicesByGroup[group] || []).length,
    devices: (devicesStore.devicesByGroup[group] || []).map(d => d.device_name),
  }))
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
      <h1 class="text-3xl font-bold text-gray-900">Groups</h1>
      <p class="text-gray-500 mt-1">Device groups and associated repositories</p>
    </div>

    <LoadingSpinner v-if="devicesStore.loading" size="lg" class="py-12" />

    <div v-else-if="groupList.length === 0" class="card text-center py-12">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
      </svg>
      <p class="text-gray-500 text-lg">No groups configured</p>
      <p class="text-gray-400 text-sm mt-2">Add devices to create groups</p>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="group in groupList"
        :key="group.name"
        @click="selectedGroup = group.name"
        class="card-hover cursor-pointer"
      >
        <div class="flex items-start justify-between mb-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">{{ group.name }}</h3>
            <p class="text-sm text-gray-500 mt-1">{{ group.count }} {{ group.count === 1 ? "device" : "devices" }}</p>
          </div>
          <span class="inline-flex items-center justify-center h-12 w-12 rounded-lg bg-green-100">
            <span class="text-lg font-semibold text-green-600">{{ group.count }}</span>
          </span>
        </div>

        <div class="mt-4">
          <p class="text-xs text-gray-500 font-medium mb-2">Git Repository:</p>
          <p class="text-sm font-mono text-gray-600">backups/{{ group.name }}/</p>
        </div>

        <div class="mt-4">
          <p class="text-xs text-gray-500 font-medium mb-2">Devices:</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="device in group.devices.slice(0, 3)"
              :key="device"
              class="inline-block px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded"
            >
              {{ device }}
            </span>
            <span
              v-if="group.devices.length > 3"
              class="inline-block px-2 py-1 text-gray-600 text-xs"
            >
              +{{ group.devices.length - 3 }} more
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail panel -->
    <div v-if="selectedGroup" @click="selectedGroup = null" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div @click.stop class="bg-white rounded-lg shadow-xl max-w-md w-full max-h-screen overflow-y-auto">
        <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-gray-900">{{ selectedGroup }}</h2>
          <button
            @click="selectedGroup = null"
            class="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        <div class="px-6 py-4">
          <div class="mb-6">
            <h3 class="text-sm font-medium text-gray-900 mb-2">Group Details</h3>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-600">Git Repository:</span>
                <span class="font-mono text-gray-900">backups/{{ selectedGroup }}/</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">Total Devices:</span>
                <span class="font-medium text-gray-900">{{ (devicesStore.devicesByGroup[selectedGroup] || []).length }}</span>
              </div>
            </div>
          </div>

          <div>
            <h3 class="text-sm font-medium text-gray-900 mb-2">Devices in this Group</h3>
            <div class="space-y-2">
              <div
                v-for="device in devicesStore.devicesByGroup[selectedGroup] || []"
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
