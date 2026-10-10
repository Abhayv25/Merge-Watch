terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "mergewatch", ManagedBy = "terraform" }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name = "mergewatch"
  ssm_parameter_arns = compact([
    "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.github_token_parameter}",
    var.webhook_parameter == "" ? "" : "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.webhook_parameter}",
  ])
}

# --- Image registry ------------------------------------------------------------

resource "aws_ecr_repository" "mergewatch" {
  name                 = local.name
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "keep_recent" {
  repository = aws_ecr_repository.mergewatch.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 5 most recent images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
      action       = { type = "expire" }
    }]
  })
}

# --- Notification state ------------------------------------------------------

resource "aws_dynamodb_table" "notified" {
  name         = "${local.name}-notified"
  billing_mode = "PAY_PER_REQUEST" # pennies at this volume, no capacity to manage
  hash_key     = "collision_key"

  attribute {
    name = "collision_key"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# --- Lambda --------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name_prefix        = "${local.name}-lambda-"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Least privilege: three DynamoDB actions on one table, read access to the
# two secrets. No access keys anywhere; Lambda supplies temporary credentials.
data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "NotificationState"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.notified.arn]
  }
  statement {
    sid       = "Secrets"
    actions   = ["ssm:GetParameter"]
    resources = local.ssm_parameter_arns
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "mergewatch"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "mergewatch" {
  function_name = local.name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.mergewatch.repository_url}:${var.image_tag}"
  architectures = ["arm64"]
  timeout       = 300
  memory_size   = 1024

  # /tmp holds the cached bare clone of the watched repository.
  ephemeral_storage {
    size = 2048
  }

  environment {
    variables = {
      MERGEWATCH_REPOSITORY         = var.repository
      MERGEWATCH_BASE_BRANCH        = var.base_branch
      MERGEWATCH_TABLE              = aws_dynamodb_table.notified.name
      MERGEWATCH_GITHUB_TOKEN_PARAM = var.github_token_parameter
      MERGEWATCH_WEBHOOK_PARAM      = var.webhook_parameter
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy_attachment.logs]
}

# --- Schedule ------------------------------------------------------------------
# EventBridge Scheduler fires on time, unlike GitHub Actions' best-effort cron.

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name_prefix        = "${local.name}-scheduler-"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-mergewatch"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.mergewatch.arn
    }]
  })
}

resource "aws_scheduler_schedule" "every_15_minutes" {
  name                = local.name
  schedule_expression = "rate(${var.interval_minutes} minutes)"
  state               = var.enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.mergewatch.arn
    role_arn = aws_iam_role.scheduler.arn
    retry_policy {
      maximum_retry_attempts = 0 # the next scheduled run is the retry
    }
  }
}

# --- Alerting ------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  count = var.alert_email == "" ? 0 : 1
  name  = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "failures" {
  alarm_name          = "${local.name}-failing"
  alarm_description   = "Mergewatch failed twice in a row (GitHub API, git fetch, or webhook problems)."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.mergewatch.function_name }
  statistic           = "Sum"
  period              = var.interval_minutes * 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alert_email == "" ? [] : [aws_sns_topic.alerts[0].arn]
}
