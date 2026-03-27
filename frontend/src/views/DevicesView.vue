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
const selectedStatus = ref<string>("")
const searchName = ref<string>("")
const showEnabledOnly = ref<boolean>(false)
const currentLayout = ref<LayoutType>("detailed")
const showFilters = ref<boolean>(true)

const LAYOUT_STORAGE_KEY = "devices-layout"

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

  if (selectedStatus.value) {
    devices = devices.filter(d => d.status === selectedStatus.value)
  }

  if (searchName.value) {
    const search = searchName.value.toLowerCase()
    devices = devices.filter(d => d.device_name.toLowerCase().includes(search))
  }

  if (showEnabledOnly.value) {
    devices = devices.filter(d => d.enabled)
  }

  return devices
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
  selectedStatus.value = ""
  searchName.value = ""
  showEnabledOnly.value = false
}

async function handleReload() {
  await devicesStore.reloadDevices()
}

onMounted(async () => {
  await Promise.all([
    devicesStore.fetchDevices(),
    devicesStore.fetchGroups(),
  ])

  // Load layout preference from localStorage
  const savedLayout = localStorage.getItem(LAYOUT_STORAGE_KEY) as LayoutType | null
  if (savedLayout && ["detailed", "compact", "list"].includes(savedLayout)) {
    currentLayout.value = savedLayout
  }
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

        <!-- Always visible: Search -->
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
        </div>

        <!-- Collapsible: Additional filters -->
        <div v-show="showFilters" class="space-y-4">
          <!-- Group filter -->
          <div class="flex flex-col md:flex-row gap-4">
            <div class="flex-1">
              <label class="label">Filter by Group</label>
              <select v-model="selectedGroup" class="input">
                <option value="">All Groups</option>
                <option v-for="group in devicesStore.groups" :key="group" :value="group">
                  {{ group }}
                </option>
              </select>
            </div>
          </div>

          <!-- Second row: Vendor and SSH Profile -->
          <div class="flex flex-col md:flex-row gap-4">
            <div class="flex-1">
              <label class="label">Filter by Vendor</label>
              <select v-model="selectedVendor" class="input">
                <option value="">All Vendors</option>
                <option v-for="vendor in devicesStore.uniqueVendors" :key="vendor" :value="vendor">
                  {{ vendor }}
                </option>
              </select>
            </div>
            <div class="flex-1">
              <label class="label">Filter by SSH Profile</label>
              <select v-model="selectedSshProfile" class="input">
                <option value="">All Profiles</option>
                <option v-for="profile in devicesStore.uniqueSshProfiles" :key="profile" :value="profile">
                  {{ profile }}
                </option>
              </select>
            </div>
          </div>

          <!-- Third row: Status and Enabled toggle -->
          <div class="flex flex-col md:flex-row gap-4">
            <div class="flex-1">
              <label class="label">Filter by Status</label>
              <select v-model="selectedStatus" class="input">
                <option value="">All Status</option>
                <option value="unknown">Unknown</option>
                <option value="backup_success">Backup Success</option>
                <option value="backup_failed">Backup Failed</option>
                <option value="backup_in_progress">Backup In Progress</option>
              </select>
            </div>
            
            <div class="flex-1 flex items-end">
              <label class="flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  v-model="showEnabledOnly"
                  class="w-4 h-4 text-downtown-600 rounded border-gray-300 focus:ring-downtown-500"
                >
                <span class="ml-2 text-sm text-gray-700">Show enabled only</span>
              </label>

              <button
                v-if="selectedGroup || selectedVendor || selectedSshProfile || selectedStatus || searchName || showEnabledOnly"
                @click="clearFilters"
                class="ml-auto text-sm text-downtown-600 hover:text-downtown-700 font-medium"
              >
                Clear filters
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Device count -->
    <div class="mb-4 text-sm text-gray-500">
      Showing {{ filteredDevices.length }} of {{ devicesStore.deviceCount }} devices
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
      <p v-if="selectedGroup || selectedVendor || selectedSshProfile || selectedStatus || searchName || showEnabledOnly" class="text-gray-400 text-sm mt-2">
        Try adjusting your filters
      </p>
    </div>

    <!-- Detailed view (grid of cards) -->
    <div
      v-else-if="currentLayout === 'detailed'"
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <div
        v-for="device in filteredDevices"
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
        v-for="device in filteredDevices"
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
        <div
          v-for="device in filteredDevices"
          :key="device.device_name"
          @click="goToDevice(device.device_name)"
          class="cursor-pointer hover:bg-gray-50 transition"
        >
          <DeviceListRow :device="device" />
        </div>
      </div>
    </div>
  </div>
</template>
