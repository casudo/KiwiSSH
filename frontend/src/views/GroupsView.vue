<script setup lang="ts">
import { onMounted, computed, ref, watch } from "vue"
import { useDevicesStore } from "@/stores/devices"
import { groupApi, type GroupWithConfig } from "@/api/groups"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

type LayoutType = "card" | "list" | "table"

interface GroupsFilterState {
  searchQuery: string
  pageSize: number
}

const devicesStore = useDevicesStore()
const selectedGroup = ref<string | null>(null)
const searchQuery = ref("")
const currentLayout = ref<LayoutType>("card")
const pageSize = ref<number>(12)
const currentPage = ref<number>(1)
const groupsLoading = ref(false)

const LAYOUT_STORAGE_KEY = "groups-layout"
const FILTERS_STORAGE_KEY = "groups-filters"

interface GroupInfo {
  name: string
  count: number
  devices: string[]
  remoteUrl: string | null
}

const configuredGroups = ref<GroupWithConfig[]>([])

const allGroups = computed((): GroupInfo[] => {
  // If we have configured groups from API, use only those
  if (configuredGroups.value.length > 0) {
    return configuredGroups.value
      .map(group => ({
        name: group.name,
        count: (devicesStore.devicesByGroup[group.name] || []).length,
        devices: (devicesStore.devicesByGroup[group.name] || []).map(d => d.device_name),
        remoteUrl: group.git_remote_url,
      }))
      .sort((a, b) => b.count - a.count)
  }
  
  // Fallback: use device-derived groups if no configured groups
  const groups = devicesStore.groups.map(group => ({
    name: group,
    count: (devicesStore.devicesByGroup[group] || []).length,
    devices: (devicesStore.devicesByGroup[group] || []).map(d => d.device_name),
    remoteUrl: null,
  }))
  return groups.sort((a, b) => b.count - a.count)
})

const selectedGroupInfo = computed((): GroupInfo | null => {
  if (!selectedGroup.value) {
    return null
  }
  return allGroups.value.find(group => group.name === selectedGroup.value) || null
})

const filteredGroups = computed((): GroupInfo[] => {
  let groups = [...allGroups.value]

  // Filter by search query
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    groups = groups.filter(g => 
      g.name.toLowerCase().includes(query) ||
      g.devices.some(d => d.toLowerCase().includes(query))
    )
  }

  return groups
})

const totalPages = computed(() => Math.ceil(filteredGroups.value.length / pageSize.value))

const groupList = computed((): GroupInfo[] => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredGroups.value.slice(start, end)
})

function setLayout(layout: LayoutType) {
  currentLayout.value = layout
  localStorage.setItem(LAYOUT_STORAGE_KEY, layout)
}

function saveFilterPreferences() {
  const state: GroupsFilterState = {
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
    const parsed = JSON.parse(rawState) as Partial<GroupsFilterState>
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

  groupsLoading.value = true
  try {
    if (devicesStore.devices.length === 0) {
      await Promise.all([
        devicesStore.fetchDevices(),
        devicesStore.fetchGroups(),
      ])
    }

    // Fetch configured groups from API
    configuredGroups.value = await groupApi.getAllWithConfig()

    // Load layout preference from localStorage
    const savedLayout = localStorage.getItem(LAYOUT_STORAGE_KEY) as LayoutType | null
    if (savedLayout && ["card", "list", "table"].includes(savedLayout)) {
      currentLayout.value = savedLayout
    }
  } finally {
    groupsLoading.value = false
  }
})
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white">Groups</h1>
      <p class="text-gray-500 dark:text-gray-400 mt-1">Device groups and associated repositories</p>
    </div>

    <LoadingSpinner v-if="devicesStore.loading || groupsLoading" size="lg" class="py-12" />

    <div v-else-if="groupList.length === 0 && !searchQuery">
      <div class="card text-center py-12">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
        </svg>
        <p class="text-gray-500 dark:text-gray-400 text-lg">No groups configured</p>
        <p class="text-gray-400 dark:text-gray-500 text-sm mt-2">Add devices to create groups</p>
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
              <label class="label">Search groups or devices</label>
              <input
                v-model="searchQuery"
                type="text"
                placeholder="e.g., network, infrastructure..."
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
          v-for="group in groupList"
          :key="group.name"
          @click="selectedGroup = group.name"
          class="card-hover cursor-pointer"
        >
          <div class="flex items-start justify-between mb-4">
            <div>
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white">{{ group.name }}</h3>
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ group.count }} {{ group.count === 1 ? "device" : "devices" }}</p>
            </div>
            <span class="inline-flex items-center justify-center h-12 w-12 rounded-lg bg-green-100 dark:bg-green-900">
              <span class="text-lg font-semibold text-green-600 dark:text-green-400">{{ group.count }}</span>
            </span>
          </div>

          <div class="mt-4">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-medium mb-2">Remote Git Repository:</p>
            <p
              v-if="group.remoteUrl"
              class="text-sm font-mono text-gray-600 dark:text-gray-400 break-all"
            >
              {{ group.remoteUrl }}
            </p>
            <p v-else class="text-sm text-gray-500 dark:text-gray-400">Not configured</p>
          </div>

          <div class="mt-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-medium mb-2">Local Repository:</p>
            <p class="text-sm font-mono text-gray-600 dark:text-gray-400">backups/{{ group.name }}/</p>
          </div>

          <div class="mt-4">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-medium mb-2">Devices:</p>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="device in group.devices.slice(0, 5)"
                :key="device"
                class="inline-block px-2 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded"
              >
                {{ device }}
              </span>
              <span
                v-if="group.devices.length > 5"
                class="inline-block px-2 py-1 text-gray-600 dark:text-gray-400 text-xs"
              >
                +{{ group.devices.length - 5 }} more
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Compact View -->
      <div v-else-if="currentLayout === 'list'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <div
          v-for="group in groupList"
          :key="group.name"
          @click="selectedGroup = group.name"
          class="card-hover cursor-pointer py-3 px-4"
        >
          <h3 class="font-semibold text-gray-900 dark:text-white text-sm mb-1">{{ group.name }}</h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">{{ group.count }} {{ group.count === 1 ? "device" : "devices" }}</p>
          <span class="inline-block px-2 py-1 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded text-xs font-medium">
            {{ group.count }}
          </span>
        </div>
      </div>

      <!-- Table View -->
      <div v-else-if="currentLayout === 'table'" class="card">
        <!-- Header row -->
        <div class="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <div class="w-full grid grid-cols-[2fr_1fr_2fr] gap-4 px-6 py-3 text-sm">
            <div class="font-semibold text-gray-700 dark:text-gray-300">Group</div>
            <div class="font-semibold text-gray-700 dark:text-gray-300 text-center">Device Count</div>
            <div class="font-semibold text-gray-700 dark:text-gray-300">Remote Repository</div>
          </div>
        </div>
        <!-- Group rows -->
        <div
          v-for="group in groupList"
          :key="group.name"
          @click="selectedGroup = group.name"
          class="border-b border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition last:border-b-0"
        >
          <div class="w-full grid grid-cols-[2fr_1fr_2fr] gap-4 px-6 py-3 text-sm">
            <div class="font-medium text-gray-900 dark:text-white truncate">{{ group.name }}</div>
            <div class="text-center text-gray-600 dark:text-gray-400">{{ group.count }}</div>
            <div class="text-gray-600 dark:text-gray-400 text-xs font-mono truncate">
              {{ group.remoteUrl || "Not configured" }}
            </div>
          </div>
        </div>
      </div>

      <!-- No Results -->
      <div v-if="filteredGroups.length === 0 && searchQuery" class="card text-center py-12">
        <p class="text-gray-500 dark:text-gray-400">No groups match your search</p>
      </div>

      <!-- Pagination controls -->
      <div v-if="filteredGroups.length > 0" class="mt-4 flex items-center justify-between">
        <span class="text-sm text-gray-600 dark:text-gray-400">
          Page {{ currentPage }} of {{ totalPages }} ({{ filteredGroups.length }} total)
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

    <!-- Detail panel -->
    <div v-if="selectedGroup" @click="selectedGroup = null" class="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div @click.stop class="bg-white dark:bg-gray-800 rounded-lg shadow-xl dark:shadow-gray-900 max-w-4xl w-full max-h-[80vh] overflow-y-auto">
        <div class="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white">{{ selectedGroup }}</h2>
          <button
            @click="selectedGroup = null"
            class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-400"
          >
            ✕
          </button>
        </div>

        <div class="px-6 py-4">
          <!-- Info Section -->
          <div class="mb-6">
            <h3 class="text-sm font-medium text-gray-900 dark:text-white mb-3">Group Info</h3>
            <div class="space-y-2 text-sm">
              <div>
                <span class="text-gray-600 dark:text-gray-400">Remote Repository:</span>
                <p
                  v-if="selectedGroupInfo?.remoteUrl"
                  class="font-mono text-gray-900 dark:text-gray-100 text-xs mt-1 break-all"
                >
                  {{ selectedGroupInfo.remoteUrl }}
                </p>
                <p v-else class="text-gray-500 dark:text-gray-400 text-xs mt-1">Not configured</p>
              </div>
              <div>
                <span class="text-gray-600 dark:text-gray-400">Local Repository:</span>
                <p class="font-mono text-gray-900 dark:text-gray-100 text-xs mt-1">backups/{{ selectedGroup }}/</p>
              </div>
              <div>
                <span class="text-gray-600 dark:text-gray-400">Total Devices:</span>
                <p class="font-medium text-gray-900 dark:text-gray-100">{{ (devicesStore.devicesByGroup[selectedGroup] || []).length }}</p>
              </div>
            </div>
          </div>

          <!-- Devices Grid (2 columns) -->
          <div>
            <h3 class="text-sm font-medium text-gray-900 dark:text-white mb-3">Devices in this Group</h3>
            <div class="grid grid-cols-2 gap-3 max-h-96 overflow-y-auto">
              <div
                v-for="device in (devicesStore.devicesByGroup[selectedGroup] || []).slice(0, 20)"
                :key="device.device_name"
                class="p-2 bg-gray-50 dark:bg-gray-700 rounded text-sm"
              >
                <p class="font-medium text-gray-900 dark:text-white">{{ device.device_name }}</p>
                <p class="text-gray-500 dark:text-gray-400 text-xs">{{ device.ip_address }} ({{ device.vendor }})</p>
              </div>
            </div>
            <div v-if="(devicesStore.devicesByGroup[selectedGroup] || []).length > 20" class="text-xs text-gray-500 dark:text-gray-400 px-2 py-2 mt-2">
              +{{ (devicesStore.devicesByGroup[selectedGroup] || []).length - 20 }} more devices
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
