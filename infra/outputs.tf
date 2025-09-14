
output "network_subnet" {
  description = "Subnet of the created Docker network"
  value       = tolist(docker_network.iac_network.ipam_config)[0].subnet
}

output "deployed_services" {
  description = "List of deployed service names"
  value       = keys(var.services)
}

output "service_details" {
  description = "Details of deployed services"
  value = {
    for name, service in var.services : name => {
      slug         = service.slug
      service_name = service.service_name
      image_name   = service.image_name
      entrypoint   = service.entrypoint
    }
  }
}
