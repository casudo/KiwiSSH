<script setup lang="ts">
import { onMounted, computed, ref, watch } from "vue"
import { useDevicesStore } from "@/stores/devices"
import { vendorApi } from "@/api/vendors"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

type LayoutType = "card" | "list" | "table"

interface VendorsFilterState {
  searchQuery: string
  pageSize: number
}

const devicesStore = useDevicesStore()
const selectedVendor = ref<string | null>(null)  // Stores vendor ID (e.g., 'cisco_ios')
const searchQuery = ref("")
const currentLayout = ref<LayoutType>("card")
const pageSize = ref<number>(12)
const currentPage = ref<number>(1)
const vendorsLoading = ref(false)

const LAYOUT_STORAGE_KEY = "vendors-layout"
const FILTERS_STORAGE_KEY = "vendors-filters"

interface VendorInfo {
  id: string
  name: string
  description?: string
  count: number
  devices: string[]
}

const configuredVendors = ref<Array<{id: string; name: string; description: string}>>([])

const allVendors = computed((): VendorInfo[] => {
  if (configuredVendors.value.length > 0) {
    return configuredVendors.value
      .map(vendor => ({
        id: vendor.id,
        name: vendor.name,
        description: vendor.description,
        count: (devicesStore.devicesByVendor[vendor.id] || []).length,
        devices: (devicesStore.devicesByVendor[vendor.id] || []).map(d => d.device_name),
      }))
      .sort((a, b) => b.count - a.count)
  }
  
  // Fallback: use device-derived vendors if no configured vendors
  const vendors = devicesStore.uniqueVendors.map(vendor => ({
    id: vendor,
    name: vendor,
    count: (devicesStore.devicesByVendor[vendor] || []).length,
    devices: (devicesStore.devicesByVendor[vendor] || []).map(d => d.device_name),
  }))
  return vendors.sort((a, b) => b.count - a.count)
})

const filteredVendors = computed((): VendorInfo[] => {
  let vendors = [...allVendors.value]

  // Filter by search query
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    vendors = vendors.filter(v => 
      v.name.toLowerCase().includes(query) ||
      v.devices.some(d => d.toLowerCase().includes(query))
    )
  }

  return vendors
})

const totalPages = computed(() => Math.ceil(filteredVendors.value.length / pageSize.value))

const vendorList = computed((): VendorInfo[] => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredVendors.value.slice(start, end)
})

const selectedVendorInfo = computed(() => 
  allVendors.value.find(v => v.id === selectedVendor.value) || null
)

function setLayout(layout: LayoutType) {
  currentLayout.value = layout
  localStorage.setItem(LAYOUT_STORAGE_KEY, layout)
}

function saveFilterPreferences() {
  const state: VendorsFilterState = {
    searchQuery: searchQuery.value,
    pageSize: pageSize.value,
  }

  localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(state))
}

function restoreFilterPreferences() {
  const rawState = localStorage.getItem(FILTERS_STORAGE_KEY)
  if (!rawState) {
    return
  }

  try {
    const parsed = JSON.parse(rawState) as Partial<VendorsFilterState>
    const validPageSizes = new Set([6, 12, 24, 50])

    if (typeof parsed.searchQuery === "string") {
      searchQuery.value = parsed.searchQuery
    }

    if (typeof parsed.pageSize === "number" && validPageSizes.has(parsed.pageSize)) {
      pageSize.value = parsed.pageSize
    }
  } catch {
    localStorage.removeItem(FILTERS_STORAGE_KEY)
  }
}

function handlePageSizeChange() {
  currentPage.value = 1
}

watch(searchQuery, () => {
  currentPage.value = 1
})

watch([searchQuery, pageSize], () => {
  saveFilterPreferences()
})

watch(totalPages, (value) => {
  const maxPage = Math.max(1, value)
  if (currentPage.value > maxPage) {
    currentPage.value = maxPage
  }
})

onMounted(async () => {
  restoreFilterPreferences()

  vendorsLoading.value = true
  try {
    if (devicesStore.devices.length === 0) {
      await Promise.all([
        devicesStore.fetchDevices(),
        devicesStore.fetchGroups(),
      ])
    }

    // Fetch configured vendors from API
    configuredVendors.value = await vendorApi.getAll()

    // Load layout preference from localStorage
    const savedLayout = localStorage.getItem(LAYOUT_STORAGE_KEY) as LayoutType | null
    if (savedLayout && ["card", "list", "table"].includes(savedLayout)) {
      currentLayout.value = savedLayout
    }
  } finally {
    vendorsLoading.value = false
  }
})
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white">Vendors</h1>
      <p class="text-gray-500 dark:text-gray-400 mt-1">Vendor configurations and assigned devices</p>
    </div>

    <LoadingSpinner v-if="devicesStore.loading || vendorsLoading" size="lg" class="py-12" />

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
              ? 'bg-kiwissh-600 text-white'
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
              ? 'bg-kiwissh-600 text-white'
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
              ? 'bg-kiwissh-600 text-white'
              : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
          ]"
        >
          List
        </button>
      </div>

      <!-- Filters -->
      <div class="card mb-6">
        <div class="space-y-4">
          <!-- Header-->
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Filters</h3>
          </div>

          <!-- Filter -->
          <div class="flex flex-col md:flex-row gap-4">
            <div class="flex-1">
              <label class="label">Search vendors or devices</label>
              <input
                v-model="searchQuery"
                type="text"
                placeholder="e.g., Cisco, Fortinet..."
                class="input"
              />
            </div>
            <div class="flex-1 flex flex-col">
              <label class="label">Entries per page</label>
              <select v-model.number="pageSize" @change="handlePageSizeChange" class="input">
                <option :value="6">6</option>
                <option :value="12">12</option>
                <option :value="24">24</option>
                <option :value="50">50</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- Card View -->
      <div v-if="currentLayout === 'card'" class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div
          v-for="vendor in vendorList"
          :key="vendor.id"
          @click="selectedVendor = vendor.id"
          class="card-hover cursor-pointer"
        >
          <div class="flex items-start justify-between mb-4">
            <div>
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white">{{ vendor.name }}</h3>
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ vendor.count }} {{ vendor.count === 1 ? "device" : "devices" }}</p>
            </div>
            <span class="inline-flex items-center justify-center h-12 w-12 rounded-lg bg-kiwissh-100 dark:bg-kiwissh-900">
              <span class="text-lg font-semibold text-kiwissh-600 dark:text-kiwissh-400">{{ vendor.count }}</span>
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
          :key="vendor.id"
          @click="selectedVendor = vendor.id"
          class="card-hover cursor-pointer py-3 px-4"
        >
          <h3 class="font-semibold text-gray-900 dark:text-white text-sm mb-1">{{ vendor.name }}</h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">{{ vendor.count }} {{ vendor.count === 1 ? "device" : "devices" }}</p>
          <span class="inline-block px-2 py-1 bg-kiwissh-100 dark:bg-kiwissh-900 text-kiwissh-700 dark:text-kiwissh-300 rounded text-xs font-medium">
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
          :key="vendor.id"
          @click="selectedVendor = vendor.id"
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
      <div v-if="filteredVendors.length === 0 && searchQuery" class="card text-center py-12">
        <p class="text-gray-500 dark:text-gray-400">No vendors match your search</p>
      </div>

      <!-- Pagination controls -->
      <div v-if="filteredVendors.length > 0" class="mt-4 flex items-center justify-between">
        <span class="text-sm text-gray-600 dark:text-gray-400">
          Page {{ currentPage }} of {{ totalPages }} ({{ filteredVendors.length }} total)
        </span>
        <div class="flex gap-2">
          <button
            @click="currentPage = Math.max(1, currentPage - 1)"
            :disabled="currentPage === 1"
            class="btn btn-secondary py-1 px-3 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            ← Previous
          </button>
          <button
            @click="currentPage = Math.min(totalPages, currentPage + 1)"
            :disabled="currentPage === totalPages"
            class="btn btn-secondary py-1 px-3 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next →
          </button>
        </div>
      </div>

      <!-- Detail panel -->
      <div v-if="selectedVendor" @click="selectedVendor = null" class="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
        <div @click.stop class="bg-white dark:bg-gray-800 rounded-lg shadow-xl dark:shadow-gray-900 max-w-4xl w-full max-h-[80vh] overflow-y-auto">
          <div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4 flex items-center justify-between">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">{{ selectedVendorInfo?.name }}</h2>
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
                  <span class="text-gray-600 dark:text-gray-400">Vendor ID:</span>
                  <span class="font-medium text-gray-900 dark:text-gray-100 font-mono">{{ selectedVendor }}</span>
                </div>
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
                  class="p-2 bg-gray-50 dark:bg-gray-700 rounded text-sm min-w-0"
                >
                  <p class="font-medium text-gray-900 dark:text-white truncate">{{ device.device_name }}</p>
                  <p class="text-gray-500 dark:text-gray-400 text-xs truncate">{{ device.ip_address }}</p>
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
