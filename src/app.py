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

def write_log(action, details):
    """Записує лог операції у S3"""
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
    """Перевіряє доступність URL HEAD-запитом (★ бонусна логіка)"""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status < 400
    except Exception:
        return False

def handler(event, context):
    try:
        http_method = event["requestContext"]["http"]["method"]

        if http_method == "POST":
            body = json.loads(event.get("body") or "{}")
            url  = body.get("url", "")
            tags = body.get("tags", [])

            if not url:
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"message": "Field 'url' is required"})
                }

            # ★ Перевірка доступності URL
            reachable = check_url_reachable(url)

            item_id = str(uuid.uuid4())
            item = {
                "id":         item_id,
                "url":        url,
                "tags":       tags,
                "reachable":  reachable,
                "created_at": datetime.now().isoformat()
            }
            table.put_item(Item=item)

            # Лог у S3
            write_log("POST /links", {
                "item_id":   item_id,
                "url":       url,
                "tags":      tags,
                "reachable": reachable
            })

            return {
                "statusCode": 201,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "id":        item_id,
                    "url":       url,
                    "reachable": reachable,
                    "tags":      tags
                })
            }

        elif http_method == "GET":
            params     = event.get("queryStringParameters") or {}
            tag_filter = params.get("tag")

            response = table.scan()
            items    = response.get("Items", [])

            if tag_filter:
                items = [i for i in items if tag_filter in i.get("tags", [])]

            # Лог у S3
            write_log("GET /links", {
                "tag_filter":    tag_filter,
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
        # Спроба залогувати помилку у S3
        try:
            write_log("ERROR", {"error": str(e)})
        except Exception:
            pass
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Internal Server Error"})
        }