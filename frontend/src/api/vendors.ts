import api from "./index"

export const vendorApi = {
  async getAll(includeConfig: boolean = false): Promise<Array<{ id: string; name: string }>> {
    const response = await api.get<{ count: number; vendors: Array<{ id: string; name: string }> }>("/vendors", {
      params: { include_config: includeConfig }
    })
    return response.data.vendors
  },

  async getDetails(vendorId: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/vendors/${vendorId}`)
    return response.data
  },

  async getCommands(vendorId: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/vendors/${vendorId}/commands`)
    return response.data
  },
}
