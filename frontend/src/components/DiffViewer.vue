<script setup lang="ts">
import { computed } from "vue"

interface DiffLine {
  type: "context" | "added" | "removed" | "header"
  content: string
  lineNum?: string
}

interface Props {
  diffContent: string
  linesAdded: number
  linesRemoved: number
}

const props = defineProps<Props>()

// Parse unified diff format
const parsedDiff = computed((): { left: DiffLine[]; right: DiffLine[] } => {
  const leftLines: DiffLine[] = []
  const rightLines: DiffLine[] = []

  if (!props.diffContent) return { left: leftLines, right: rightLines }

  const lines = props.diffContent.split("\n")
  let leftLineNum = 0
  let rightLineNum = 0

  for (const line of lines) {
    if (line.startsWith("---") || line.startsWith("+++") || line.startsWith("@@")) {
      // Header lines - show on both sides
      leftLines.push({ type: "header", content: line })
      rightLines.push({ type: "header", content: line })
    } else if (line.startsWith("-")) {
      // Removed line - show only on left
      leftLines.push({
        type: "removed",
        content: line.substring(1),
        lineNum: String(leftLineNum++),
      })
    } else if (line.startsWith("+")) {
      // Added line - show only on right
      rightLines.push({
        type: "added",
        content: line.substring(1),
        lineNum: String(rightLineNum++),
      })
    } else if (line === "") {
      // Empty line
      leftLines.push({ type: "context", content: "", lineNum: String(leftLineNum++) })
      rightLines.push({ type: "context", content: "", lineNum: String(rightLineNum++) })
    } else {
      // Context line (unchanged)
      leftLines.push({ type: "context", content: line.substring(1), lineNum: String(leftLineNum++) })
      rightLines.push({ type: "context", content: line.substring(1), lineNum: String(rightLineNum++) })
    }
  }

  return { left: leftLines, right: rightLines }
})

function getLineClass(type: string): string {
  switch (type) {
    case "removed":
      return "bg-red-50 border-l-4 border-red-300"
    case "added":
      return "bg-green-50 border-l-4 border-green-300"
    case "header":
      return "bg-gray-100 border-b border-gray-300 text-gray-700 font-medium text-sm"
    default:
      return "bg-white border-l-4 border-gray-200"
  }
}
</script>

<template>
  <div v-if="diffContent" class="space-y-4">
    <!-- Stats -->
    <div class="flex items-center space-x-6 text-sm">
      <span class="flex items-center space-x-2">
        <span class="text-green-600 font-medium">+{{ linesAdded }}</span>
        <span class="text-gray-600">added</span>
      </span>
      <span class="flex items-center space-x-2">
        <span class="text-red-600 font-medium">-{{ linesRemoved }}</span>
        <span class="text-gray-600">removed</span>
      </span>
    </div>

    <!-- Side-by-side diff viewer -->
    <div class="border border-gray-200 rounded-lg overflow-hidden">
      <div class="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x lg:divide-gray-200">
        <!-- Left side (From/Removed) -->
        <div class="font-mono text-sm bg-white overflow-x-auto">
          <div class="min-w-max">
            <div class="sticky top-0 bg-gray-50 border-b border-gray-200 px-4 py-2 font-medium text-gray-700 text-xs">
              Original (Removed lines in red)
            </div>
            <div
              v-for="(line, idx) in parsedDiff.left"
              :key="`left-${idx}`"
              :class="getLineClass(line.type)"
              class="flex"
            >
              <div v-if="line.type !== 'header'" class="flex-shrink-0 w-12 px-3 py-1 text-right text-gray-500 bg-gray-50 select-none border-r border-gray-200 text-xs">
                {{ line.lineNum }}
              </div>
              <div v-else class="flex-shrink-0 w-12" />
              <pre class="flex-1 px-4 py-1 text-gray-800 whitespace-pre-wrap break-words">{{
                line.content
              }}</pre>
            </div>
          </div>
        </div>

        <!-- Right side (To/Added) -->
        <div class="font-mono text-sm bg-white overflow-x-auto">
          <div class="min-w-max">
            <div class="sticky top-0 bg-gray-50 border-b border-gray-200 px-4 py-2 font-medium text-gray-700 text-xs">
              Modified (Added lines in green)
            </div>
            <div
              v-for="(line, idx) in parsedDiff.right"
              :key="`right-${idx}`"
              :class="getLineClass(line.type)"
              class="flex"
            >
              <div v-if="line.type !== 'header'" class="flex-shrink-0 w-12 px-3 py-1 text-right text-gray-500 bg-gray-50 select-none border-r border-gray-200 text-xs">
                {{ line.lineNum }}
              </div>
              <div v-else class="flex-shrink-0 w-12" />
              <pre class="flex-1 px-4 py-1 text-gray-800 whitespace-pre-wrap break-words">{{
                line.content
              }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="text-center text-gray-500 py-8">
    <p>No diff available</p>
    <p class="text-sm mt-1">Select two commits to view differences</p>
  </div>
</template>
