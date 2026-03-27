<script setup lang="ts">
// Settings view - placeholder for future implementation
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900">Settings</h1>
      <p class="text-gray-500 mt-1">Configure Project Downtown</p>
    </div>

    <div class="card">
      <div class="text-center py-12">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        <p class="text-gray-500 text-lg">Settings coming soon</p>
        <p class="text-gray-400 text-sm mt-2">
          Configuration is currently managed through YAML files in the config directory.
        </p>
      </div>

      <!-- Configuration info -->
      <div class="mt-8 border-t pt-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Configuration Files</h2>
        <div class="space-y-3 text-sm">
          <div class="flex items-start">
            <code class="bg-gray-100 px-2 py-1 rounded text-downtown-700 font-mono">config/downtown.yaml</code>
            <span class="ml-3 text-gray-600">Main application configuration</span>
          </div>
          <div class="flex items-start">
            <code class="bg-gray-100 px-2 py-1 rounded text-downtown-700 font-mono">config/ssh_profiles.yaml</code>
            <span class="ml-3 text-gray-600">SSH connection profiles</span>
          </div>
          <div class="flex items-start">
            <code class="bg-gray-100 px-2 py-1 rounded text-downtown-700 font-mono">config/vendors/</code>
            <span class="ml-3 text-gray-600">Vendor-specific backup instructions</span>
          </div>
          <div class="flex items-start">
            <code class="bg-gray-100 px-2 py-1 rounded text-downtown-700 font-mono">config/sources/devices.csv</code>
            <span class="ml-3 text-gray-600">Device inventory</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
