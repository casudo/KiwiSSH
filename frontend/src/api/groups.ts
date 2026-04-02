import api from "./index"

export interface GroupWithConfig {
  name: string
  config: Record<string, unknown>
  git_remote_url: string | null
}

export const groupApi = {
  async getAll(params?: Record<string, string>): Promise<string[]> {
    const response = await api.get<{ count: number; groups: string[] }>("/groups", { params })
    return response.data.groups
  },

  async getAllWithConfig(): Promise<GroupWithConfig[]> {
    const response = await api.get<{ count: number; groups: GroupWithConfig[] }>("/groups", {
      params: { include_config: true }
    })
    return response.data.groups
  },

  async getDetails(groupName: string, includeConfig: boolean = false): Promise<Record<string, unknown>> {
    const response = await api.get(`/groups/${groupName}`, {
      params: { include_config: includeConfig }
    })
    return response.data
  },
}
