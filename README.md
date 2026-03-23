```markdown
# Lab 4 - AWS Serverless | Варіант 3: Рейтинг посилань

Безсерверний REST API на AWS за допомогою Terraform.
Стек: API Gateway → Lambda (Python 3.12) → DynamoDB

## Запуск

```bash
# 1. Створити S3-бакет для стану
aws s3api create-bucket --bucket tf-state-lab4-surname-name-03 \
  --region eu-central-1 \
  --create-bucket-configuration LocationConstraint=eu-central-1

# 2. Розгорнути
cd envs/dev/
terraform init && terraform apply -auto-approve

# 3. Тестування
export API_URL=$(terraform output -raw api_url)
curl -X POST $API_URL/links -H "Content-Type: application/json" \
  -d '{"url": "https://aws.amazon.com", "tags": ["cloud"]}'
curl -X GET "$API_URL/links?tag=cloud"

# 4. Видалити після захисту
terraform destroy -auto-approve
```

## Endpoints

| Метод | Шлях | Опис |
|-------|------|------|
| POST | /links | Зберегти URL + мітки (★ перевіряє доступність) |
| GET | /links?tag= | Отримати посилання з фільтром за міткою |
```