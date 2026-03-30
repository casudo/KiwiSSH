import api from "./index"

export const favoritesApi = {
  async getAll(): Promise<string[]> {
    const response = await api.get<{ count: number; favorites: string[] }>("/favorites")
    return response.data.favorites || []
  },

  async add(deviceName: string): Promise<void> {
    await api.put(`/favorites/${encodeURIComponent(deviceName)}`)
  },

  async remove(deviceName: string): Promise<void> {
    await api.delete(`/favorites/${encodeURIComponent(deviceName)}`)
  },
}
