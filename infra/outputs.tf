output "ecr_repository_url" {
  value = aws_ecr_repository.mergewatch.repository_url
}

output "lambda_function_name" {
  value = aws_lambda_function.mergewatch.function_name
}

output "state_table" {
  value = aws_dynamodb_table.notified.name
}

output "log_group" {
  value = aws_cloudwatch_log_group.lambda.name
}
