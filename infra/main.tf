terraform {
  required_version = ">= 1.0"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  host = "unix:///var/run/docker.sock"
}

# Create the main network for all services
resource "docker_network" "iac_network" {
  name = var.network_name
  driver = "bridge"
  ipam_config {
    subnet = "172.20.0.0/16"
  }
}

# Data source for the base Python image
data "docker_registry_image" "python_base" {
  name = "python:3.11-slim"
}

# Data source for the Envoy image
data "docker_registry_image" "envoy" {
  name = "envoyproxy/envoy:v1.28-latest"
}

# Local variables for common tags
locals {
  app_image_tag = "iac-app:latest"
  envoy_image_tag = "iac-envoy:latest"
}

# Output the network name for use by the application
output "network_name" {
  value = docker_network.iac_network.name
}

output "network_id" {
  value = docker_network.iac_network.id
}
