import api from "./index"

export interface VendorRedactionPattern {
  search: string
  replacement?: string
}

// "processing" section of a vendor YAML, every part of it is optional
export interface VendorProcessing {
  strip_patterns?: string[]
  config_start?: string
  config_end?: string
  redaction?: {
    enabled?: boolean
    patterns?: VendorRedactionPattern[]
  }
}

// Vendor YAML without its "commands" section
export interface VendorDetails {
  vendor: { id: string; name: string; description?: string }
  processing?: VendorProcessing
  [key: string]: unknown
}

export const vendorApi = {
  async getAll(includeConfig: boolean = false): Promise<Array<{ id: string; name: string }>> {
    const response = await api.get<{ count: number; vendors: Array<{ id: string; name: string }> }>("/vendors", {
      params: { include_config: includeConfig }
    })
    return response.data.vendors
  },

  async getDetails(vendorId: string): Promise<VendorDetails> {
    const response = await api.get<VendorDetails>(`/vendors/${encodeURIComponent(vendorId)}`)
    return response.data
  },

  async getCommands(vendorId: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/vendors/${vendorId}/commands`)
    return response.data
  },
}
