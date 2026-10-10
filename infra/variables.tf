variable "region" {
  type    = string
  default = "us-east-1"
}

variable "repository" {
  description = "Repository to watch, as owner/repo."
  type        = string
}

variable "base_branch" {
  type    = string
  default = "main"
}

variable "image_tag" {
  description = "Tag of the image pushed to the mergewatch ECR repository."
  type        = string
  default     = "latest"
}

variable "github_token_parameter" {
  description = "Name of the SSM SecureString holding a GitHub token with read access to pull requests and contents."
  type        = string
  default     = "/mergewatch/github-token"
}

variable "webhook_parameter" {
  description = "Name of the SSM SecureString holding the Discord or Slack webhook URL. Empty prints alerts to the logs only."
  type        = string
  default     = "/mergewatch/webhook-url"
}

variable "interval_minutes" {
  type    = number
  default = 15
}

variable "enabled" {
  description = "Set to false to pause the schedule without destroying anything."
  type        = bool
  default     = true
}

variable "alert_email" {
  description = "Email to notify when runs keep failing. Empty disables email alerts."
  type        = string
  default     = ""
}
