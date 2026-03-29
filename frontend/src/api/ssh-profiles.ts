import api from "./index"

export const sshProfileApi = {
  async getAll(includeConfig: boolean = false): Promise<string[]> {
    const response = await api.get<{ count: number; ssh_profiles: string[] | Array<{ name: string }> }>("/ssh-profiles", {
      params: { include_config: includeConfig }
    })
    const data = response.data.ssh_profiles
    if (includeConfig && Array.isArray(data) && data.length > 0 && typeof data[0] === "object") {
      return (data as Array<{ name: string }>).map(p => p.name)
    }
    return data as string[]
  },

  async getDetails(profileName: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/ssh-profiles/${profileName}`)
    return response.data
  },
}
