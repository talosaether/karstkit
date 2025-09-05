variable "network_name" {
  description = "Name of the Docker network for all services"
  type        = string
  default     = "iacnet"
}

variable "grpc_port" {
  description = "Default gRPC port for services"
  type        = number
  default     = 50051
}

variable "envoy_inbound_port" {
  description = "Envoy inbound port"
  type        = number
  default     = 15000
}

variable "envoy_outbound_port" {
  description = "Envoy outbound port"
  type        = number
  default     = 15001
}

variable "envoy_metrics_port" {
  description = "Envoy metrics port"
  type        = number
  default     = 9901
}

variable "services" {
  description = "Map of services to deploy"
  type = map(object({
    slug        = string
    service_name = string
    image_name  = string
    entrypoint  = optional(string)
    environment = optional(map(string), {})
    volumes     = optional(list(string), [])
  }))
  default = {}
}

variable "secrets_path" {
  description = "Path to secrets directory"
  type        = string
  default     = "../secrets"
}
