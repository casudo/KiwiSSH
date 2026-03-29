<script setup lang="ts">
import { onMounted, computed, ref } from "vue"
import { useDevicesStore } from "@/stores/devices"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

type LayoutType = "card" | "list" | "table"

const devicesStore = useDevicesStore()
const selectedProfile = ref<string | null>(null)
const searchQuery = ref("")
const currentLayout = ref<LayoutType>("card")
const pageSize = ref<number>(12)
const currentPage = ref<number>(1)

const LAYOUT_STORAGE_KEY = "ssh-profiles-layout"

interface SSHProfileInfo {
  name: string
  count: number
  devices: string[]
}

const allProfiles = computed((): SSHProfileInfo[] => {
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
    .sort((a, b) => b.count - a.count)
})

const filteredProfiles = computed((): SSHProfileInfo[] => {
  let list = [...allProfiles.value]

  // Filter by search query
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    list = list.filter(p =>
      p.name.toLowerCase().includes(query) ||
      p.devices.some(d => d.toLowerCase().includes(query))
    )
  }

  return list
})

const totalPages = computed(() => Math.ceil(filteredProfiles.value.length / pageSize.value))

const sshProfileList = computed((): SSHProfileInfo[] => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredProfiles.value.slice(start, end)
})

function setLayout(layout: LayoutType) {
  currentLayout.value = layout
  localStorage.setItem(LAYOUT_STORAGE_KEY, layout)
}

function handlePageSizeChange() {
  currentPage.value = 1
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
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white">SSH Profiles</h1>
      <p class="text-gray-500 dark:text-gray-400 mt-1">SSH connection profiles and assigned devices</p>
    </div>

    <LoadingSpinner v-if="devicesStore.loading" size="lg" class="py-12" />

    <div v-else-if="sshProfileList.length === 0 && !searchQuery">
      <div class="card text-center py-12">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        <p class="text-gray-500 dark:text-gray-400 text-lg">No SSH profiles configured</p>
        <p class="text-gray-400 dark:text-gray-500 text-sm mt-2">Add devices to see SSH profiles</p>
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
            <!-- Header-->
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Filters</h3>
          </div>

          <!-- Filters row -->
          <div class="flex flex-col md:flex-row gap-4">
            <div class="flex-1">
              <label class="label">Search profiles or devices</label>
              <input
                v-model="searchQuery"
                type="text"
                placeholder="e.g., default, remote..."
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
          v-for="profile in sshProfileList"
          :key="profile.name"
          @click="selectedProfile = profile.name"
          class="card-hover cursor-pointer"
        >
          <div class="flex items-start justify-between mb-4">
            <div>
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white capitalize">{{ profile.name }}</h3>
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ profile.count }} {{ profile.count === 1 ? "device" : "devices" }}</p>
            </div>
            <span class="inline-flex items-center justify-center h-12 w-12 rounded-lg bg-purple-100 dark:bg-purple-900">
              <span class="text-lg font-semibold text-purple-600 dark:text-purple-400">{{ profile.count }}</span>
            </span>
          </div>

          <div class="mt-4">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-medium mb-2">Used by:</p>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="device in profile.devices.slice(0, 5)"
                :key="device"
                class="inline-block px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded"
              >
                {{ device }}
              </span>
              <span
                v-if="profile.devices.length > 5"
                class="inline-block px-2 py-1 text-gray-600 dark:text-gray-400 text-xs"
              >
                +{{ profile.devices.length - 5 }} more
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Compact View -->
      <div v-else-if="currentLayout === 'list'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <div
          v-for="profile in sshProfileList"
          :key="profile.name"
          @click="selectedProfile = profile.name"
          class="card-hover cursor-pointer py-3 px-4"
        >
          <h3 class="font-semibold text-gray-900 dark:text-white text-sm mb-1 capitalize">{{ profile.name }}</h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">{{ profile.count }} {{ profile.count === 1 ? "device" : "devices" }}</p>
          <span class="inline-block px-2 py-1 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 rounded text-xs font-medium">
            {{ profile.count }}
          </span>
        </div>
      </div>

      <!-- Table View -->
      <div v-else-if="currentLayout === 'table'" class="card">
        <!-- Header row -->
        <div class="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <div class="w-full grid grid-cols-[2fr_1fr_2fr] gap-4 px-6 py-3 text-sm">
            <div class="font-semibold text-gray-700 dark:text-gray-300">SSH Profile</div>
            <div class="font-semibold text-gray-700 dark:text-gray-300 text-center">Device Count</div>
            <div class="font-semibold text-gray-700 dark:text-gray-300">Sample Devices</div>
          </div>
        </div>
        <!-- Profile rows -->
        <div
          v-for="profile in sshProfileList"
          :key="profile.name"
          @click="selectedProfile = profile.name"
          class="border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition last:border-b-0"
        >
          <div class="w-full grid grid-cols-[2fr_1fr_2fr] gap-4 px-6 py-3 text-sm">
            <div class="font-medium text-gray-900 dark:text-white capitalize truncate">{{ profile.name }}</div>
            <div class="text-center text-gray-600 dark:text-gray-400">{{ profile.count }}</div>
            <div class="text-gray-600 dark:text-gray-400 text-xs line-clamp-2">
              {{ profile.devices.slice(0, 3).join(", ") }}
              <span v-if="profile.devices.length > 3" class="text-gray-400 dark:text-gray-500">
                +{{ profile.devices.length - 3 }} more
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- No Results -->
      <div v-if="filteredProfiles.length === 0 && searchQuery" class="card text-center py-12">
        <p class="text-gray-500 dark:text-gray-400">No profiles match your search</p>
      </div>

      <!-- Pagination controls -->
      <div v-if="filteredProfiles.length > 0" class="mt-4 flex items-center justify-between">
        <span class="text-sm text-gray-600 dark:text-gray-400">
          Page {{ currentPage }} of {{ totalPages }} ({{ filteredProfiles.length }} total)
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
      <div v-if="selectedProfile" @click="selectedProfile = null" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
        <div @click.stop class="bg-white dark:bg-gray-800 rounded-lg shadow-xl dark:shadow-gray-900 max-w-4xl w-full max-h-[80vh] overflow-y-auto">
          <div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4 flex items-center justify-between">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white capitalize">{{ selectedProfile }}</h2>
            <button
              @click="selectedProfile = null"
              class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-400"
            >
              ✕
            </button>
          </div>

          <div class="px-6 py-4">
            <!-- Info Section -->
            <div class="mb-6">
              <h3 class="text-sm font-medium text-gray-900 dark:text-white mb-3">Profile Info</h3>
              <div class="space-y-2 text-sm">
                <div>
                  <span class="text-gray-600 dark:text-gray-400">Profile Name:</span>
                  <p class="font-medium text-gray-900 dark:text-gray-100 capitalize mt-1">{{ selectedProfile }}</p>
                </div>
                <div>
                  <span class="text-gray-600 dark:text-gray-400">Total Devices:</span>
                  <p class="font-medium text-gray-900 dark:text-gray-100">
                    {{ devicesStore.devices.filter(d => d.ssh_profile === selectedProfile).length }}
                  </p>
                </div>
                <div>
                  <span class="text-gray-600 dark:text-gray-400">Config file:</span>
                  <p class="text-xs text-gray-500 dark:text-gray-400">config/ssh_profiles.yaml</p>
                </div>
              </div>
            </div>

            <!-- Devices Grid (2 columns) -->
            <div>
              <h3 class="text-sm font-medium text-gray-900 dark:text-white mb-3">Devices Using This Profile</h3>
              <div class="grid grid-cols-2 gap-3 max-h-96 overflow-y-auto">
                <div
                  v-for="device in devicesStore.devices.filter(d => d.ssh_profile === selectedProfile).slice(0, 20)"
                  :key="device.device_name"
                  class="p-2 bg-gray-50 dark:bg-gray-700 rounded text-sm"
                >
                  <p class="font-medium text-gray-900 dark:text-white">{{ device.device_name }}</p>
                  <p class="text-gray-500 dark:text-gray-400 text-xs">{{ device.ip_address }} ({{ device.vendor }})</p>
                </div>
              </div>
              <div v-if="devicesStore.devices.filter(d => d.ssh_profile === selectedProfile).length > 20" class="text-xs text-gray-500 dark:text-gray-400 px-2 py-2 mt-2">
                +{{ devicesStore.devices.filter(d => d.ssh_profile === selectedProfile).length - 20 }} more devices
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
