<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"
import type { Device } from "@/types/device"

interface Props {
  inputId: string
  devices: Device[]
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: "Search by name, group or IP...",
})

// Only changed by the user (typing or picking a device), never by a prop update
const deviceName = defineModel<string>({ required: true })

// Rendering thousands of options makes typing sluggish, the list asks to narrow down instead
const MAX_VISIBLE_OPTIONS = 100

const open = ref(false)
// The full list is shown when opening, so another device can be picked without clearing the current one first
const filterActive = ref(false)
const highlightedIndex = ref(-1)
const listbox = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)

const listboxId = computed(() => `${props.inputId}-listbox`)
const query = computed(() => deviceName.value.trim().toLowerCase())

const matches = computed((): Device[] => {
  const search = query.value
  if (!filterActive.value || !search) return props.devices
  return props.devices.filter((device) => (
    device.device_name.toLowerCase().includes(search)
    || device.group.toLowerCase().includes(search)
    || device.ip_address.toLowerCase().includes(search)
  ))
})
// The device name is split around the typed text, so the match can be highlighted
const visibleOptions = computed(() => matches.value.slice(0, MAX_VISIBLE_OPTIONS).map((device) => {
  const name = device.device_name
  const start = filterActive.value && query.value ? name.toLowerCase().indexOf(query.value) : -1
  const end = start + query.value.length
  return start < 0
    ? { device, before: name, match: "", after: "" }
    : { device, before: name.slice(0, start), match: name.slice(start, end), after: name.slice(end) }
}))
const hiddenCount = computed(() => matches.value.length - visibleOptions.value.length)

function optionId(index: number): string {
  return `${props.inputId}-option-${index}`
}

function openList() {
  if (open.value) return
  open.value = true
  filterActive.value = false
  // Start on the current device, so the arrow keys continue from there
  highlightedIndex.value = visibleOptions.value.findIndex((option) => option.device.device_name === deviceName.value)
}

function closeList() {
  open.value = false
  highlightedIndex.value = -1
}

function toggleList() {
  if (open.value) {
    closeList()
  } else {
    openList()
  }
  input.value?.focus()
}

function selectDevice(device: Device) {
  deviceName.value = device.device_name
  closeList()
}

function onInput(event: Event) {
  deviceName.value = (event.target as HTMLInputElement).value
  open.value = true
  filterActive.value = true
  highlightedIndex.value = visibleOptions.value.length > 0 ? 0 : -1
}

function moveHighlight(step: number) {
  if (!open.value) {
    openList()
    return
  }
  const count = visibleOptions.value.length
  if (count === 0) return
  highlightedIndex.value = highlightedIndex.value < 0
    ? (step > 0 ? 0 : count - 1)
    : (highlightedIndex.value + step + count) % count
}

function onEnter(event: KeyboardEvent) {
  // With the list closed, Enter submits the form as usual
  if (!open.value) return
  const option = visibleOptions.value[highlightedIndex.value]
  if (option) {
    event.preventDefault()
    selectDevice(option.device)
  }
}

function onEscape(event: KeyboardEvent) {
  if (!open.value) return
  event.preventDefault()
  closeList()
}

watch(highlightedIndex, (index) => {
  if (index < 0) return
  void nextTick(() => {
    listbox.value?.querySelector(`#${CSS.escape(optionId(index))}`)?.scrollIntoView({ block: "nearest" })
  })
})
</script>

<template>
  <div class="relative">
    <input
      :id="inputId"
      ref="input"
      :value="deviceName"
      type="text"
      class="input pr-10"
      role="combobox"
      aria-autocomplete="list"
      :aria-expanded="open"
      :aria-controls="listboxId"
      :aria-activedescendant="open && highlightedIndex >= 0 ? optionId(highlightedIndex) : undefined"
      :placeholder="placeholder"
      autocomplete="off"
      spellcheck="false"
      @input="onInput"
      @click="openList"
      @blur="closeList"
      @keydown.down.prevent="moveHighlight(1)"
      @keydown.up.prevent="moveHighlight(-1)"
      @keydown.enter="onEnter"
      @keydown.esc="onEscape"
    />
    <button
      type="button"
      tabindex="-1"
      class="absolute inset-y-0 right-0 flex items-center px-3 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
      aria-label="Show devices"
      @mousedown.prevent="toggleList"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 transition-transform" :class="{ 'rotate-180': open }" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd" />
      </svg>
    </button>

    <!-- mousedown.prevent keeps the focus in the input, so picking an option doesn't close the list through the blur first -->
    <div
      v-if="open"
      class="absolute z-30 mt-1 w-full overflow-hidden rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg dark:shadow-black/40"
      @mousedown.prevent
    >
      <ul
        :id="listboxId"
        ref="listbox"
        role="listbox"
        class="max-h-72 overflow-y-auto py-1"
      >
        <li
          v-for="({ device, before, match, after }, index) in visibleOptions"
          :id="optionId(index)"
          :key="device.device_name"
          role="option"
          :aria-selected="device.device_name === deviceName"
          class="cursor-pointer px-3 py-2 text-sm"
          :class="index === highlightedIndex
            ? 'bg-kiwissh-50 dark:bg-kiwissh-900/40'
            : 'hover:bg-gray-50 dark:hover:bg-slate-800/70'"
          @mousemove="highlightedIndex = index"
          @click="selectDevice(device)"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="truncate font-medium text-gray-900 dark:text-gray-100">{{ before }}<mark v-if="match" class="bg-kiwissh-100 dark:bg-kiwissh-800/70 text-inherit rounded-sm">{{ match }}</mark>{{ after }}</span>
            <svg
              v-if="device.device_name === deviceName"
              xmlns="http://www.w3.org/2000/svg"
              class="h-4 w-4 shrink-0 text-kiwissh-600 dark:text-kiwissh-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fill-rule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clip-rule="evenodd" />
            </svg>
          </div>
          <div class="truncate text-xs text-gray-500 dark:text-gray-400">
            {{ device.group }}<template v-if="device.ip_address"> · {{ device.ip_address }}</template>
          </div>
        </li>
      </ul>
      <p v-if="visibleOptions.length === 0" class="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
        No device matches "{{ deviceName.trim() }}"
      </p>
      <p
        v-else-if="hiddenCount > 0"
        class="border-t border-gray-100 dark:border-slate-800 px-3 py-2 text-xs text-gray-500 dark:text-gray-400"
      >
        {{ hiddenCount }} more device(s), keep typing to narrow down the list
      </p>
    </div>
  </div>
</template>
