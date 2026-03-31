# envs/dev/main.tf

provider "aws" {
  region = "eu-central-1"
}

locals {
  prefix = "tf-state-lab4-hryhorian-diana-03"
}

# Новий ресурс — S3 бакет для логів Lambda
resource "aws_s3_bucket" "logs" {
  bucket        = "${local.prefix}-logs"
  force_destroy = true # дозволяє видалити бакет з вмістом через terraform destroy
}

# Блокування публічного доступу до лог-бакету
resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

module "database" {
  source     = "../../modules/dynamodb"
  table_name = "${local.prefix}-links-table"
}

module "backend" {
  source              = "../../modules/lambda"
  function_name       = "${local.prefix}-links-handler"
  source_file         = "${path.root}/../../src/app.py"
  dynamodb_table_arn  = module.database.table_arn
  dynamodb_table_name = module.database.table_name

  # передаємо лог-бакет у модуль lambda
  log_bucket_name = aws_s3_bucket.logs.bucket
  log_bucket_arn  = aws_s3_bucket.logs.arn
}

module "api" {
  source               = "../../modules/api_gateway"
  api_name             = "${local.prefix}-links-api"
  lambda_invoke_arn    = module.backend.invoke_arn
  lambda_function_name = module.backend.function_name
}

output "api_url" {
  value = module.api.api_endpoint
}

# Вивід імені лог-бакету для зручної перевірки
output "log_bucket" {
  value = aws_s3_bucket.logs.bucket
}