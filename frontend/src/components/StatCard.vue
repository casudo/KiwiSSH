<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(
  defineProps<{
    title: string
    value: number | string
    color?: "downtown" | "green" | "red" | "yellow" | "gray" | "blue" | "purple" | "orange"
    icon?: string | null
  }>(),
  {
    color: "downtown",
    icon: null,
  }
)

const colorClasses: Record<string, string> = {
  downtown: "text-downtown-600 dark:text-downtown-400",
  green: "text-green-600 dark:text-green-400",
  red: "text-red-600 dark:text-red-400",
  yellow: "text-yellow-600 dark:text-yellow-400",
  gray: "text-gray-700 dark:text-gray-300",
  blue: "text-blue-600 dark:text-blue-400",
  purple: "text-purple-600 dark:text-purple-400",
  orange: "text-orange-600 dark:text-orange-400",
}

const textColorClass = computed(() => colorClasses[props.color] || colorClasses.downtown)
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">{{ title }}</h3>
      <slot name="icon">
        <span v-if="icon" class="text-gray-400 dark:text-gray-500">{{ icon }}</span>
      </slot>
    </div>
    <p class="text-3xl font-bold mt-2" :class="textColorClass">
      {{ value }}
    </p>
    <slot name="footer"></slot>
  </div>
</template>
