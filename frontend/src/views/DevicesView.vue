<script setup lang="ts">
import { ref, onMounted, computed } from "vue"
import { useRouter } from "vue-router"
import { useDevicesStore } from "@/stores/devices"
import DeviceCard from "@/components/DeviceCard.vue"
import DeviceCompactCard from "@/components/DeviceCompactCard.vue"
import DeviceListRow from "@/components/DeviceListRow.vue"
import LoadingSpinner from "@/components/LoadingSpinner.vue"
import type { Device } from "@/types/device"

const router = useRouter()
const devicesStore = useDevicesStore()

type LayoutType = "detailed" | "compact" | "list"

const selectedGroup = ref<string>("")
const selectedVendor = ref<string>("")
const selectedSshProfile = ref<string>("")
const selectedStatus = ref<string[]>([])
const searchName = ref<string>("")
const searchIP = ref<string>("")
const showEnabledOnly = ref<boolean>(false)
const currentLayout = ref<LayoutType>("detailed")
const showFilters = ref<boolean>(false)
const currentPage = ref<number>(1)
const pageSize = ref<number>(50)
const showStatusDropdown = ref<boolean>(false)

const LAYOUT_STORAGE_KEY = "devices-layout"

const statusOptions = [
  { value: "unknown", label: "Unknown" },
  { value: "backup_in_progress", label: "Backup In Progress" },
  { value: "backup_success", label: "Backup Success" },
  { value: "backup_failed", label: "Backup Failed" },
  { value: "backup_no_changes", label: "No Changes" },
]

const filteredDevices = computed((): Device[] => {
  let devices = devicesStore.devices

  if (selectedGroup.value) {
    devices = devices.filter(d => d.group === selectedGroup.value)
  }

  if (selectedVendor.value) {
    devices = devices.filter(d => d.vendor === selectedVendor.value)
  }

  if (selectedSshProfile.value) {
    devices = devices.filter(d => d.ssh_profile === selectedSshProfile.value)
  }

  if (selectedStatus.value.length > 0) {
    devices = devices.filter(d => selectedStatus.value.includes(d.status))
  }

  if (searchName.value) {
    const search = searchName.value.toLowerCase()
    devices = devices.filter(d => d.device_name.toLowerCase().includes(search))
  }

  if (searchIP.value) {
    const search = searchIP.value.toLowerCase()
    devices = devices.filter(d => d.ip_address.toLowerCase().includes(search))
  }

  if (showEnabledOnly.value) {
    devices = devices.filter(d => d.enabled)
  }

  return devices
})

const totalPages = computed(() => Math.ceil(filteredDevices.value.length / pageSize.value))

const paginatedDevices = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredDevices.value.slice(start, end)
})

function goToDevice(deviceName: string) {
  router.push(`/devices/${deviceName}`)
}

function setLayout(layout: LayoutType) {
  currentLayout.value = layout
  localStorage.setItem(LAYOUT_STORAGE_KEY, layout)
}

function clearFilters() {
  selectedGroup.value = ""
  selectedVendor.value = ""
  selectedSshProfile.value = ""
  selectedStatus.value = []
  searchName.value = ""
  searchIP.value = ""
  showEnabledOnly.value = false
  currentPage.value = 1
}

function handlePageSizeChange() {
  currentPage.value = 1
}

function toggleStatusFilter(value: string) {
  if (selectedStatus.value.includes(value)) {
    selectedStatus.value = selectedStatus.value.filter(s => s !== value)
  } else {
    selectedStatus.value.push(value)
  }
}

function removeStatusFilter(value: string) {
  selectedStatus.value = selectedStatus.value.filter(s => s !== value)
}

async function handleReload() {
  await devicesStore.reloadDevices()
}

onMounted(async () => {
  await Promise.all([
    devicesStore.fetchDevices(),
    devicesStore.fetchGroups(),
    devicesStore.fetchVendors(),
  ])

  // Load layout preference from localStorage
  const savedLayout = localStorage.getItem(LAYOUT_STORAGE_KEY) as LayoutType | null
  if (savedLayout && ["detailed", "compact", "list"].includes(savedLayout)) {
    currentLayout.value = savedLayout
  }

  // Close dropdown when clicking outside
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    if (!target.closest('[data-status-filter]')) {
      showStatusDropdown.value = false
    }
  })
})
</script>

<template>
  <div>
    <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-8">
      <div>
        <h1 class="text-3xl font-bold text-gray-900">Devices</h1>
        <p class="text-gray-500 mt-1">Manage your network devices</p>
      </div>
      <div class="mt-4 md:mt-0">
        <button @click="handleReload" class="btn btn-secondary" :disabled="devicesStore.loading">
          Reload Devices from Source
        </button>
      </div>
    </div>

    <!-- Layout Toggle -->
    <div class="flex gap-2 mb-6">
      <button
        @click="setLayout('compact')"
        :class="[
          'px-4 py-2 rounded font-medium text-sm transition',
          currentLayout === 'compact'
            ? 'bg-downtown-600 text-white'
            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
        ]"
      >
        Compact
      </button>
      <button
        @click="setLayout('detailed')"
        :class="[
          'px-4 py-2 rounded font-medium text-sm transition',
          currentLayout === 'detailed'
            ? 'bg-downtown-600 text-white'
            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
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
            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
        ]"
      >
        List
      </button>
    </div>

    <!-- Filters -->
    <div class="card mb-6">
      <div class="space-y-4">
        <!-- Header with toggle button -->
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-gray-900">Filters</h3>
          <button
            @click="showFilters = !showFilters"
            class="text-sm text-downtown-600 hover:text-downtown-700 font-medium flex items-center gap-1"
          >
            {{ showFilters ? "▼ Hide" : "▶ Show" }} Filters
          </button>
        </div>

        <!-- Always visible: Search and entries per page -->
        <div class="flex flex-col md:flex-row gap-4">
          <div class="flex-1">
            <label class="label">Search by name</label>
            <input
              v-model="searchName"
              type="text"
              placeholder="e.g., router, switch..."
              class="input"
            />
          </div>

          <div class="flex-1">
            <label class="label">Search by IP</label>
            <input
              v-model="searchIP"
              type="text"
              placeholder="e.g., 192.168.1..."
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

        <!-- Collapsible: Additional filters -->
        <div v-show="showFilters" class="space-y-4">
          <!-- Filters in one row: Group, Vendor, SSH Profile, Status -->
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label class="label">Filter by Group</label>
              <select v-model="selectedGroup" class="input">
                <option value="">All Groups</option>
                <option v-for="group in devicesStore.groups" :key="group" :value="group">
                  {{ group }}
                </option>
              </select>
            </div>
            <div>
              <label class="label">Filter by Vendor</label>
              <select v-model="selectedVendor" class="input">
                <option value="">All Vendors</option>
                <option v-for="vendor in devicesStore.uniqueVendors" :key="vendor" :value="vendor">
                  {{ vendor }}
                </option>
              </select>
            </div>
            <div>
              <label class="label">Filter by SSH Profile</label>
              <select v-model="selectedSshProfile" class="input">
                <option value="">All Profiles</option>
                <option v-for="profile in devicesStore.uniqueSshProfiles" :key="profile" :value="profile">
                  {{ profile }}
                </option>
              </select>
            </div>
            <div data-status-filter>
              <label class="label">Filter by Status</label>
              <div class="relative">
                <!-- Tag input field -->
                <div class="input h-[39px] min-h-[39px] max-h-[39px] flex flex-nowrap items-center gap-2 overflow-x-auto overflow-y-hidden whitespace-nowrap py-1 cursor-text" @click="showStatusDropdown = !showStatusDropdown">
                  <div
                    v-for="status in selectedStatus"
                    :key="status"
                    class="shrink-0 flex items-center gap-2 bg-downtown-100 text-downtown-700 px-3 py-1 rounded-full text-sm font-medium"
                  >
                    {{ statusOptions.find(o => o.value === status)?.label || status }}
                    <button
                      type="button"
                      @click.stop="removeStatusFilter(status)"
                      class="hover:text-downtown-900 font-bold"
                    >
                      ×
                    </button>
                  </div>
                  <span v-if="selectedStatus.length === 0" class="text-gray-400 text-sm">Select statuses...</span>
                </div>

                <!-- Dropdown menu -->
                <div
                  v-if="showStatusDropdown"
                  class="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-300 rounded shadow-lg z-10 max-h-48 overflow-y-auto"
                >
                  <label
                    v-for="option in statusOptions"
                    :key="option.value"
                    class="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-b-0"
                  >
                    <input
                      type="checkbox"
                      :checked="selectedStatus.includes(option.value)"
                      @change="() => toggleStatusFilter(option.value)"
                      class="w-4 h-4 text-downtown-600 rounded border-gray-300 focus:ring-downtown-500"
                    />
                    <span class="text-sm text-gray-700">{{ option.label }}</span>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- Show enabled only and Clear filters button -->
          <div class="flex items-center justify-between">
            <label class="flex items-center cursor-pointer">
              <input
                type="checkbox"
                v-model="showEnabledOnly"
                class="w-4 h-4 text-downtown-600 rounded border-gray-300 focus:ring-downtown-500"
              >
              <span class="ml-2 text-sm text-gray-700">Show enabled only</span>
            </label>

            <button
              v-if="selectedGroup || selectedVendor || selectedSshProfile || selectedStatus.length > 0 || searchName || searchIP || showEnabledOnly"
              @click="clearFilters"
              class="text-sm text-downtown-600 hover:text-downtown-700 font-medium"
            >
              Clear filters
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Device list -->
    <LoadingSpinner v-if="devicesStore.loading" size="lg" class="py-12" />

    <div v-else-if="devicesStore.error" class="card text-center py-8">
      <p class="text-red-600">{{ devicesStore.error }}</p>
      <button @click="devicesStore.fetchDevices()" class="btn btn-primary mt-4">
        Retry
      </button>
    </div>

    <div v-else-if="filteredDevices.length === 0" class="card text-center py-12">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
      <p class="text-gray-500 text-lg">No devices found</p>
      <p v-if="selectedGroup || selectedVendor || selectedSshProfile || selectedStatus.length > 0 || searchName || showEnabledOnly" class="text-gray-400 text-sm mt-2">
        Try adjusting your filters
      </p>
    </div>

    <!-- Detailed view (grid of cards) -->
    <div
      v-else-if="currentLayout === 'detailed'"
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <div
        v-for="device in paginatedDevices"
        :key="device.device_name"
        @click="goToDevice(device.device_name)"
        class="cursor-pointer"
      >
        <DeviceCard :device="device" />
      </div>
    </div>

    <!-- Compact view (small cards) -->
    <div
      v-else-if="currentLayout === 'compact'"
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3"
    >
      <div
        v-for="device in paginatedDevices"
        :key="device.device_name"
        @click="goToDevice(device.device_name)"
        class="cursor-pointer"
      >
        <DeviceCompactCard :device="device" />
      </div>
    </div>

    <!-- List view (table-like) -->
    <div v-else-if="currentLayout === 'list'" class="overflow-x-auto">
      <div class="card">
        <!-- Header row -->
        <DeviceListRow :is-header="true" />
        <!-- Device rows -->
        <div
          v-for="device in paginatedDevices"
          :key="device.device_name"
          @click="goToDevice(device.device_name)"
          class="cursor-pointer hover:bg-gray-50 transition"
        >
          <DeviceListRow :device="device" />
        </div>
      </div>
    </div>

    <!-- Pagination controls -->
    <div v-if="filteredDevices.length > 0" class="mt-4 flex items-center justify-between">
      <span class="text-sm text-gray-600">
        Page {{ currentPage }} of {{ totalPages }} ({{ filteredDevices.length }} total)
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
  </div>
</template>
