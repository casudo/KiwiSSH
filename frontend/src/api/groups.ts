import api from "./index"

export const groupApi = {
  async getAll(params?: Record<string, string>): Promise<string[]> {
    const response = await api.get<{ count: number; groups: string[] }>("/groups", { params })
    return response.data.groups
  },

  async getDetails(groupName: string, includeConfig: boolean = false): Promise<Record<string, unknown>> {
    const response = await api.get(`/groups/${groupName}`, {
      params: { include_config: includeConfig }
    })
    return response.data
  },
}
