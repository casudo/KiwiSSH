import { createApp } from "vue"
import { createPinia } from "pinia"

import App from "./App.vue"
import router from "./router"

import "./style.css"

// Versions
export const APP_VERSION = "1.1.0" // KiwiSSH backend + frontend bundled together
export const FRONTEND_VERSION = "1.1.0" // Frontend version only

function applyInitialTheme(): void {
	const themeStorageKey = "kiwissh-theme"

	try {
		const storedTheme = localStorage.getItem(themeStorageKey)
		const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
		const shouldUseDark =
			storedTheme == null ||
			storedTheme === "dark" ||
			(storedTheme === "system" && prefersDark)
		document.documentElement.classList.toggle("dark", shouldUseDark)
	} catch {
		// If localStorage or matchMedia is unavailable, default to dark mode.
		document.documentElement.classList.add("dark")
	}
}

applyInitialTheme()

const app = createApp(App)

app.provide("frontendVersion", FRONTEND_VERSION)
app.use(createPinia())
app.use(router)

app.mount("#app")
