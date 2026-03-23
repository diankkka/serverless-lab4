# src/app.py
import json
import boto3
import os
import uuid
import urllib.request
from datetime import datetime

TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

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
            url   = body.get("url", "")
            tags  = body.get("tags", [])   # список міток, наприклад ["cloud","aws"]

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

            return {
                "statusCode": 201,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"id": item_id, "url": url,
                                    "reachable": reachable, "tags": tags})
            }

        elif http_method == "GET":
            # GET /links?tag=cloud  — фільтрація за міткою
            params    = event.get("queryStringParameters") or {}
            tag_filter = params.get("tag")

            response = table.scan()
            items    = response.get("Items", [])

            if tag_filter:
                items = [i for i in items if tag_filter in i.get("tags", [])]

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
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Internal Server Error"})
        }