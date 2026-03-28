<script setup>
import Navbar from "@/components/Navbar.vue"
import Footer from "@/components/Footer.vue"
</script>

<template>
  <div class="min-h-screen bg-gray-50 flex flex-col">
    <Navbar />
    <main class="container mx-auto px-4 py-8 flex-grow">
      <RouterView />
    </main>
    <Footer />
  </div>
</template>
