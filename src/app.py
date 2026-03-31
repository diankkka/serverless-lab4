# src/app.py
import json
import boto3
import os
import uuid
import urllib.request
from datetime import datetime

TABLE_NAME = os.environ.get("TABLE_NAME")
LOG_BUCKET = os.environ.get("LOG_BUCKET")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
s3 = boto3.client("s3")

# ← НОВИЙ клієнт для Comprehend, ініціалізується поза handler (фаза INIT)
comprehend = boto3.client("comprehend", region_name="eu-central-1")


def write_log(action, details):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "details": details
    }
    key = f"logs/{datetime.now().strftime('%Y/%m/%d')}/{uuid.uuid4()}.json"
    s3.put_object(
        Bucket=LOG_BUCKET,
        Key=key,
        Body=json.dumps(log_entry, ensure_ascii=False),
        ContentType="application/json"
    )


def check_url_reachable(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status < 400
    except Exception:
        return False


def handler(event, context):
    try:
        http_method = event["requestContext"]["http"]["method"]
        path = event.get("rawPath", "")
        path_params = event.get("pathParameters") or {}

        # ← НОВИЙ маршрут: GET /links/{id}/language
        if http_method == "GET" and path.endswith("/language"):
            parts = path.strip("/").split("/")
            link_id = parts[1] if len(parts) >= 3 else None
            if not link_id:
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"message": "Missing link id"})
                }

            # Отримуємо запис з DynamoDB
            result = table.get_item(Key={"id": link_id})
            item = result.get("Item")
            if not item:
                return {
                    "statusCode": 404,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"message": "Link not found"})
                }

            # Текст для аналізу — url + теги як рядок
            tags_raw = item.get("tags", [])
            # якщо tags_raw — список словників {"S": ...} (старі записи), перетворюємо
            if tags_raw and isinstance(tags_raw[0], dict) and "S" in tags_raw[0]:
                tags = [t["S"] for t in tags_raw]
            else:
                tags = tags_raw  # вже список рядків
            text_to_analyze = item.get("url", "") + " " + " ".join(tags)

            # Мінімум 1 символ потрібен
            if not text_to_analyze.strip():
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"message": "No text to analyze"})
                }
            languages = []
            language_code = "unknown"
            confidence = 0.0
            
            try:
                lang_result = comprehend.detect_dominant_language(
                    Text=text_to_analyze[:4900]  # ліміт 5000 байт
                )
                languages = lang_result.get("Languages", [])
                top_lang = languages[0] if languages else {}
                language_code = top_lang.get("LanguageCode", "unknown")
                confidence = round(top_lang.get("Score", 0.0), 4)
            except Exception as e:
                language_code = "unknown"
                confidence = 0.0
                print(f"Comprehend error: {str(e)}")

            # Зберігаємо результат назад у DynamoDB
            table.update_item(
                Key={"id": link_id},
                UpdateExpression="SET language_code = :lc, language_confidence = :cf",
                ExpressionAttributeValues={
                    ":lc": language_code,
                    ":cf": str(confidence)
                }
            )

            write_log("GET /links/{id}/language", {
                "link_id": link_id,
                "language_code": language_code,
                "confidence": confidence
            })

            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "id": link_id,
                    "language_code": language_code,
                    "confidence": confidence,
                    "all_languages": languages
                })
            }

        # ── Старі маршрути без змін ──────────────────────────────────────────

        if http_method == "POST":
            body = json.loads(event.get("body") or "{}")
            url = body.get("url", "")
            tags = body.get("tags", [])

            if not url:
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"message": "Field 'url' is required"})
                }

            reachable = check_url_reachable(url)
            item_id = str(uuid.uuid4())
            item = {
                "id": item_id,
                "url": url,
                "tags": tags,
                "reachable": reachable,
                "created_at": datetime.now().isoformat()
            }
            table.put_item(Item=item)

            write_log("POST /links", {
                "item_id": item_id,
                "url": url,
                "tags": tags,
                "reachable": reachable
            })

            return {
                "statusCode": 201,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "id": item_id,
                    "url": url,
                    "reachable": reachable,
                    "tags": tags
                })
            }

        elif http_method == "GET":
            params = event.get("queryStringParameters") or {}
            tag_filter = params.get("tag")

            response = table.scan()
            items = response.get("Items", [])

            if tag_filter:
                items = [i for i in items if tag_filter in i.get("tags", [])]

            write_log("GET /links", {
                "tag_filter": tag_filter,
                "results_count": len(items)
            })

            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"links": items})
            }

        return {
            "statusCode": 405,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Method Not Allowed"})
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        try:
            write_log("ERROR", {"error": str(e)})
        except Exception:
            pass
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Internal Server Error"})
        }