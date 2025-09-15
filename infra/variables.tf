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

variable "expose_ports" {
  description = "Map of common web ports to expose from containers to host"
  type = map(object({
    internal_port = number
    external_port = number
    protocol     = optional(string, "tcp")
  }))
  default = {
    "flask_dev" = {
      internal_port = 5000
      external_port = 5000
    }
    "http_alt" = {
      internal_port = 8000
      external_port = 8000
    }
    "flask_admin" = {
      internal_port = 8080
      external_port = 8080
    }
    "node_dev" = {
      internal_port = 3000
      external_port = 3000
    }
    "alt_dev" = {
      internal_port = 4000
      external_port = 4000
    }
    "prometheus" = {
      internal_port = 9000
      external_port = 9000
    }
  }
}
