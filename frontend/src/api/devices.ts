import api from "./index"
import type { Device } from "@/types/device"

export const deviceApi = {
  async getAll(params?: Record<string, string>): Promise<Device[]> {
    const response = await api.get<Device[]>("/devices", { params })
    return response.data
  },

  async getByName(deviceName: string): Promise<Device> {
    const response = await api.get<Device>(`/devices/${deviceName}`)
    return response.data
  },

  async getStatus(deviceName: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/devices/${deviceName}/status`)
    return response.data
  },

  async getGroups(): Promise<{ groups: string[]; count: number }> {
    const response = await api.get("/devices/groups")
    return response.data
  },

  async reload(): Promise<Record<string, unknown>> {
    const response = await api.post("/devices/reload")
    return response.data
  },
}
