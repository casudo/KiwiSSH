import api from "./index"
import type { Device } from "@/types/device"

export const deviceApi = {
  async getAll(params?: Record<string, string>): Promise<Device[]> {
    const queryParams = { ...params, include_config: "true" }
    const response = await api.get<{ count: number; devices: Device[] }>("/devices", { params: queryParams })
    return response.data.devices
  },

  async getByName(deviceName: string): Promise<Device> {
    const response = await api.get<Device>(`/devices/${deviceName}`)
    return response.data
  },

  async reload(): Promise<Record<string, unknown>> {
    const response = await api.post("/devices/reload")
    return response.data
  },
}
