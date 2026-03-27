<script setup lang="ts">
import { onMounted, computed, ref } from "vue"
import { useDevicesStore } from "@/stores/devices"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

const devicesStore = useDevicesStore()
const selectedVendor = ref<string | null>(null)

interface VendorInfo {
  name: string
  count: number
  devices: string[]
}

const vendorList = computed((): VendorInfo[] => {
  return devicesStore.uniqueVendors.map(vendor => ({
    name: vendor,
    count: (devicesStore.devicesByVendor[vendor] || []).length,
    devices: (devicesStore.devicesByVendor[vendor] || []).map(d => d.device_name),
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
      <h1 class="text-3xl font-bold text-gray-900">Vendors</h1>
      <p class="text-gray-500 mt-1">Vendor configurations and assigned devices</p>
    </div>

    <LoadingSpinner v-if="devicesStore.loading" size="lg" class="py-12" />

    <div v-else-if="vendorList.length === 0" class="card text-center py-12">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.452a6 6 0 00-3.86.3l-2.387.452a2 2 0 00-1.021.547m19.428-3.068a6 6 0 00-.3-2.6m0 0a6 6 0 00-1.371-3.561m0 0a6 6 0 00-5.571-2.585m0 0a6 6 0 00-5.571 2.585m0 0a6 6 0 00-1.371 3.561m0 0a6 6 0 00-.3 2.6" />
      </svg>
      <p class="text-gray-500 text-lg">No vendors configured</p>
      <p class="text-gray-400 text-sm mt-2">Add devices to see vendors</p>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="vendor in vendorList"
        :key="vendor.name"
        @click="selectedVendor = vendor.name"
        class="card-hover cursor-pointer"
      >
        <div class="flex items-start justify-between mb-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">{{ vendor.name }}</h3>
            <p class="text-sm text-gray-500 mt-1">{{ vendor.count }} {{ vendor.count === 1 ? "device" : "devices" }}</p>
          </div>
          <span class="inline-flex items-center justify-center h-12 w-12 rounded-lg bg-downtown-100">
            <span class="text-lg font-semibold text-downtown-600">{{ vendor.count }}</span>
          </span>
        </div>

        <div class="mt-4">
          <p class="text-xs text-gray-500 font-medium mb-2">Assigned to:</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="device in vendor.devices.slice(0, 3)"
              :key="device"
              class="inline-block px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded"
            >
              {{ device }}
            </span>
            <span
              v-if="vendor.devices.length > 3"
              class="inline-block px-2 py-1 text-gray-600 text-xs"
            >
              +{{ vendor.devices.length - 3 }} more
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail panel -->
    <div v-if="selectedVendor" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div class="bg-white rounded-lg shadow-xl max-w-md w-full max-h-screen overflow-y-auto">
        <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-gray-900">{{ selectedVendor }}</h2>
          <button
            @click="selectedVendor = null"
            class="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        <div class="px-6 py-4">
          <div class="mb-6">
            <div>
              <h3 class="text-sm font-medium text-gray-900 mb-2">Details</h3>
              <div class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <span class="text-gray-600">Total Devices:</span>
                  <span class="font-medium text-gray-900">{{ (devicesStore.devicesByVendor[selectedVendor] || []).length }}</span>
                </div>
              </div>
            </div>
          </div>

          <h3 class="text-sm font-medium text-gray-900 mb-2">Assigned Devices</h3>
          <div class="space-y-2">
            <div
              v-for="device in devicesStore.devicesByVendor[selectedVendor] || []"
              :key="device.device_name"
              class="p-3 bg-gray-50 rounded text-sm"
            >
              <p class="font-medium text-gray-900">{{ device.device_name }}</p>
              <p class="text-gray-500 text-xs">{{ device.ip_address }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
