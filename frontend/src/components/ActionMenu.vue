<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"

export interface ActionMenuItem {
  id: string
  label: string
  // SVG path (24x24 viewBox, stroked) shown in front of the label
  icon?: string
  title?: string
  disabled?: boolean
  // Shows a spinner instead of the icon, and a dot on the menu button while the menu is closed
  busy?: boolean
  onSelect: () => void
}

const props = withDefaults(defineProps<{
  items: ActionMenuItem[]
  label?: string
}>(), {
  label: "More actions",
})

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLElement | null>(null)

const anyBusy = computed(() => props.items.some(item => item.busy))

// Read from the DOM, refs collected in a v-for don't keep the order of the items
function enabledButtons(): HTMLButtonElement[] {
  return Array.from(menu.value?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [])
}

async function openMenu(focus: "first" | "last" = "first") {
  open.value = true
  await nextTick()
  const buttons = enabledButtons()
  ;(focus === "first" ? buttons[0] : buttons[buttons.length - 1])?.focus()
}

function closeMenu(returnFocus = false) {
  if (!open.value) return
  open.value = false
  if (returnFocus) trigger.value?.focus()
}

function toggleMenu() {
  if (open.value) {
    closeMenu()
  } else {
    void openMenu()
  }
}

function selectItem(item: ActionMenuItem) {
  if (item.disabled) return
  closeMenu(true)
  item.onSelect()
}

function onTriggerKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault()
    void openMenu(event.key === "ArrowDown" ? "first" : "last")
  }
}

function onMenuKeydown(event: KeyboardEvent) {
  const buttons = enabledButtons()
  if (buttons.length === 0) return
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement)

  switch (event.key) {
    case "ArrowDown":
      event.preventDefault()
      buttons[(index + 1) % buttons.length].focus()
      break
    case "ArrowUp":
      event.preventDefault()
      buttons[(index - 1 + buttons.length) % buttons.length].focus()
      break
    case "Home":
      event.preventDefault()
      buttons[0].focus()
      break
    case "End":
      event.preventDefault()
      buttons[buttons.length - 1].focus()
      break
    case "Escape":
      event.preventDefault()
      closeMenu(true)
      break
    case "Tab":
      closeMenu()
      break
  }
}

function onDocumentPointerDown(event: PointerEvent) {
  if (root.value && !root.value.contains(event.target as Node)) {
    closeMenu()
  }
}

// Only listen while open, so a page with several menus doesn't pay for the closed ones
watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener("pointerdown", onDocumentPointerDown)
  } else {
    document.removeEventListener("pointerdown", onDocumentPointerDown)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown)
})
</script>

<template>
  <div ref="root" class="relative">
    <button
      ref="trigger"
      type="button"
      @click="toggleMenu"
      @keydown="onTriggerKeydown"
      class="btn btn-secondary px-3 relative"
      :class="{ 'ring-2 ring-kiwissh-500': open }"
      :aria-label="label"
      :title="label"
      aria-haspopup="menu"
      :aria-expanded="open"
    >
      <!-- Line-height box, so the button is as tall as the text buttons next to it -->
      <span class="flex h-6 items-center">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </span>
      <!-- Something in the menu is still running, e.g. a device test whose dialog was closed -->
      <span
        v-if="anyBusy && !open"
        class="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-kiwissh-500 ring-2 ring-white dark:ring-slate-900 animate-pulse"
      />
    </button>

    <Transition
      enter-active-class="transition duration-100 ease-out"
      enter-from-class="opacity-0 scale-95"
      leave-active-class="transition duration-75 ease-in"
      leave-to-class="opacity-0 scale-95"
    >
      <div
        v-if="open"
        ref="menu"
        role="menu"
        :aria-label="label"
        @keydown="onMenuKeydown"
        class="absolute right-0 z-30 mt-2 w-56 origin-top-right rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-1 shadow-lg dark:shadow-black/50"
      >
        <button
          v-for="item in items"
          :key="item.id"
          type="button"
          role="menuitem"
          :disabled="item.disabled"
          :title="item.title"
          @click="selectItem(item)"
          class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-slate-700 focus:bg-gray-100 dark:focus:bg-slate-700 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <svg
            v-if="item.busy"
            xmlns="http://www.w3.org/2000/svg"
            class="h-4 w-4 shrink-0 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <svg
            v-else-if="item.icon"
            xmlns="http://www.w3.org/2000/svg"
            class="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="item.icon" />
          </svg>
          <span v-else class="w-4 shrink-0" />
          {{ item.label }}
        </button>
      </div>
    </Transition>
  </div>
</template>
