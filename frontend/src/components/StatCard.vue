<script setup lang="ts">
import { computed } from "vue"

const props = withDefaults(
  defineProps<{
    title: string
    value: number | string
    color?: "downtown" | "green" | "red" | "yellow" | "gray"
    icon?: string | null
  }>(),
  {
    color: "downtown",
    icon: null,
  }
)

const colorClasses: Record<string, string> = {
  downtown: "text-downtown-600",
  green: "text-green-600",
  red: "text-red-600",
  yellow: "text-yellow-600",
  gray: "text-gray-700",
}

const textColorClass = computed(() => colorClasses[props.color] || colorClasses.downtown)
</script>

<template>
  <div class="card">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium text-gray-500">{{ title }}</h3>
      <slot name="icon">
        <span v-if="icon" class="text-gray-400">{{ icon }}</span>
      </slot>
    </div>
    <p class="text-3xl font-bold mt-2" :class="textColorClass">
      {{ value }}
    </p>
    <slot name="footer"></slot>
  </div>
</template>
