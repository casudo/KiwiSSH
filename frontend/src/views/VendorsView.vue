<script setup lang="ts">
import { onMounted, computed, ref } from "vue"
import { useDevicesStore } from "@/stores/devices"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

type LayoutType = "card" | "list" | "table"

const devicesStore = useDevicesStore()
const selectedVendor = ref<string | null>(null)
const searchQuery = ref("")
const currentLayout = ref<LayoutType>("card")

const LAYOUT_STORAGE_KEY = "vendors-layout"

interface VendorInfo {
  name: string
  count: number
  devices: string[]
}

const vendorList = computed((): VendorInfo[] => {
  let vendors = devicesStore.uniqueVendors.map(vendor => ({
    name: vendor,
    count: (devicesStore.devicesByVendor[vendor] || []).length,
    devices: (devicesStore.devicesByVendor[vendor] || []).map(d => d.device_name),
  }))

  // Filter by search query
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    vendors = vendors.filter(v => 
      v.name.toLowerCase().includes(query) ||
      v.devices.some(d => d.toLowerCase().includes(query))
    )
  }

  // Sort by device count (descending)
  return vendors.sort((a, b) => b.count - a.count)
})

function setLayout(layout: LayoutType) {
  currentLayout.value = layout
  localStorage.setItem(LAYOUT_STORAGE_KEY, layout)
}

onMounted(async () => {
  if (devicesStore.devices.length === 0) {
    await Promise.all([
      devicesStore.fetchDevices(),
      devicesStore.fetchGroups(),
    ])
  }

  // Load layout preference from localStorage
  const savedLayout = localStorage.getItem(LAYOUT_STORAGE_KEY) as LayoutType | null
  if (savedLayout && ["card", "list", "table"].includes(savedLayout)) {
    currentLayout.value = savedLayout
  }
})
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white">Vendors</h1>
      <p class="text-gray-500 dark:text-gray-400 mt-1">Vendor configurations and assigned devices</p>
    </div>

    <LoadingSpinner v-if="devicesStore.loading" size="lg" class="py-12" />

    <div v-else-if="vendorList.length === 0 && !searchQuery">
      <div class="card text-center py-12">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.452a6 6 0 00-3.86.3l-2.387.452a2 2 0 00-1.021.547m19.428-3.068a6 6 0 00-.3-2.6m0 0a6 6 0 00-1.371-3.561m0 0a6 6 0 00-5.571-2.585m0 0a6 6 0 00-5.571 2.585m0 0a6 6 0 00-1.371 3.561m0 0a6 6 0 00-.3 2.6" />
        </svg>
        <p class="text-gray-500 dark:text-gray-400 text-lg">No vendors configured</p>
        <p class="text-gray-400 dark:text-gray-500 text-sm mt-2">Add devices to see vendors</p>
      </div>
    </div>

    <div v-else>
      <!-- Layout Toggle -->
      <div class="flex gap-2 mb-6">
        <button
          @click="setLayout('card')"
          :class="[
            'px-4 py-2 rounded font-medium text-sm transition',
            currentLayout === 'card'
              ? 'bg-downtown-600 text-white'
              : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
          ]"
        >
          Detailed
        </button>
        <button
          @click="setLayout('list')"
          :class="[
            'px-4 py-2 rounded font-medium text-sm transition',
            currentLayout === 'list'
              ? 'bg-downtown-600 text-white'
              : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
          ]"
        >
          Compact
        </button>
        <button
          @click="setLayout('table')"
          :class="[
            'px-4 py-2 rounded font-medium text-sm transition',
            currentLayout === 'table'
              ? 'bg-downtown-600 text-white'
              : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
          ]"
        >
          List
        </button>
      </div>

      <!-- Filters -->
      <div class="card mb-6">
        <div class="space-y-4">
          <div>
            <label class="label">Search vendors or devices</label>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="e.g., Cisco, Fortinet..."
              class="input"
            />
          </div>
        </div>
      </div>

      <!-- Card View -->
      <div v-if="currentLayout === 'card'" class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div
          v-for="vendor in vendorList"
          :key="vendor.name"
          @click="selectedVendor = vendor.name"
          class="card-hover cursor-pointer"
        >
          <div class="flex items-start justify-between mb-4">
            <div>
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white">{{ vendor.name }}</h3>
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ vendor.count }} {{ vendor.count === 1 ? "device" : "devices" }}</p>
            </div>
            <span class="inline-flex items-center justify-center h-12 w-12 rounded-lg bg-downtown-100 dark:bg-downtown-900">
              <span class="text-lg font-semibold text-downtown-600 dark:text-downtown-400">{{ vendor.count }}</span>
            </span>
          </div>

          <div class="mt-4">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-medium mb-2">Assigned to:</p>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="device in vendor.devices.slice(0, 5)"
                :key="device"
                class="inline-block px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded"
              >
                {{ device }}
              </span>
              <span
                v-if="vendor.devices.length > 5"
                class="inline-block px-2 py-1 text-gray-600 dark:text-gray-400 text-xs"
              >
                +{{ vendor.devices.length - 5 }} more
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Compact View -->
      <div v-else-if="currentLayout === 'list'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <div
          v-for="vendor in vendorList"
          :key="vendor.name"
          @click="selectedVendor = vendor.name"
          class="card-hover cursor-pointer py-3 px-4"
        >
          <h3 class="font-semibold text-gray-900 dark:text-white text-sm mb-1">{{ vendor.name }}</h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">{{ vendor.count }} {{ vendor.count === 1 ? "device" : "devices" }}</p>
          <span class="inline-block px-2 py-1 bg-downtown-100 dark:bg-downtown-900 text-downtown-700 dark:text-downtown-300 rounded text-xs font-medium">
            {{ vendor.count }}
          </span>
        </div>
      </div>

      <!-- Table View -->
      <div v-else-if="currentLayout === 'table'" class="card">
        <!-- Header row -->
        <div class="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <div class="w-full grid grid-cols-[2fr_1fr_2fr] gap-4 px-6 py-3 text-sm">
            <div class="font-semibold text-gray-700 dark:text-gray-300">Vendor</div>
            <div class="font-semibold text-gray-700 dark:text-gray-300 text-center">Device Count</div>
            <div class="font-semibold text-gray-700 dark:text-gray-300">Sample Devices</div>
          </div>
        </div>
        <!-- Vendor rows -->
        <div
          v-for="vendor in vendorList"
          :key="vendor.name"
          @click="selectedVendor = vendor.name"
          class="border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition last:border-b-0"
        >
          <div class="w-full grid grid-cols-[2fr_1fr_2fr] gap-4 px-6 py-3 text-sm">
            <div class="font-medium text-gray-900 dark:text-white truncate">{{ vendor.name }}</div>
            <div class="text-center text-gray-600 dark:text-gray-400">{{ vendor.count }}</div>
            <div class="text-gray-600 dark:text-gray-400 text-xs line-clamp-2">
              {{ vendor.devices.slice(0, 3).join(", ") }}
              <span v-if="vendor.devices.length > 3" class="text-gray-400 dark:text-gray-500">
                +{{ vendor.devices.length - 3 }} more
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- No Results -->
      <div v-if="vendorList.length === 0 && searchQuery" class="card text-center py-12">
        <p class="text-gray-500 dark:text-gray-400">No vendors match your search</p>
      </div>

      <!-- Detail panel -->
      <div v-if="selectedVendor" @click="selectedVendor = null" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
        <div @click.stop class="bg-white dark:bg-gray-800 rounded-lg shadow-xl dark:shadow-gray-900 max-w-4xl w-full max-h-[80vh] overflow-y-auto">
          <div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4 flex items-center justify-between">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">{{ selectedVendor }}</h2>
            <button
              @click="selectedVendor = null"
              class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-400"
            >
              ✕
            </button>
          </div>

          <div class="px-6 py-4">
            <!-- Info Section -->
            <div class="mb-6">
              <h3 class="text-sm font-medium text-gray-900 dark:text-white mb-3">Vendor Info</h3>
              <div class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <span class="text-gray-600 dark:text-gray-400">Total Devices:</span>
                  <span class="font-medium text-gray-900 dark:text-gray-100">{{ (devicesStore.devicesByVendor[selectedVendor] || []).length }}</span>
                </div>
              </div>
            </div>

            <!-- Devices Grid (2 columns) -->
            <div>
              <h3 class="text-sm font-medium text-gray-900 dark:text-white mb-3">Assigned Devices</h3>
              <div class="grid grid-cols-2 gap-3 max-h-96 overflow-y-auto">
                <div
                  v-for="device in (devicesStore.devicesByVendor[selectedVendor] || []).slice(0, 20)"
                  :key="device.device_name"
                  class="p-2 bg-gray-50 dark:bg-gray-700 rounded text-sm"
                >
                  <p class="font-medium text-gray-900 dark:text-white">{{ device.device_name }}</p>
                  <p class="text-gray-500 dark:text-gray-400 text-xs">{{ device.ip_address }}</p>
                </div>
              </div>
              <div v-if="(devicesStore.devicesByVendor[selectedVendor] || []).length > 20" class="text-xs text-gray-500 dark:text-gray-400 px-2 py-2 mt-2">
                +{{ (devicesStore.devicesByVendor[selectedVendor] || []).length - 20 }} more devices
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
