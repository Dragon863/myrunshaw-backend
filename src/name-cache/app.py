import base64
import hashlib
import hmac
import os
import redis
from flask import Flask, request, jsonify
import json
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARN)

app = Flask(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

APPWRITE_WEBHOOK_SECRET = str.encode(os.environ.get("APPWRITE_WEBHOOK_SECRET"))

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
    )
    redis_client.ping()
    logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Could not connect to Redis: {e}")
    redis_client = None

CACHE_PREFIX = "user_name:"
CACHE_TTL_SECONDS = 60 * 60 * 24 * 7
# technically I don't need a TTL at all, but this is just in case the cache container goes down with appwrite staying up


@app.route("/webhook/appwrite/user-update", methods=["POST"])
def handle_appwrite_user_update():
    if not redis_client:
        logger.error("Redis client not available.")
        return jsonify({"error": "Cache service unavailable"}), 503

    if APPWRITE_WEBHOOK_SECRET:
        """
        From the Appwrite documentation:
        Webhooks can be verified by using the X-Appwrite-Webhook-Signature header. This is the HMAC-SHA1 signature of the payload. You can find the signature key in your webhooks properties in the dashboard. To generate this hash you append the payload to the end of webhook URL (make sure there are no spaces in between) and then use the HMAC-SHA1 algorithm to generate the signature. After you've generated the signature, compare it to the X-Appwrite-Webhook-Signature header value. If they match, the payload is valid and you can trust it came from your Appwrite instance.
        """

        signature = request.headers.get("x-appwrite-webhook-signature")
        if not signature:
            return jsonify({"error": "Bad signature request"}), 400

        payload = request.get_json()
        if payload is None:
            return jsonify({"error": "Invalid JSON"}), 400

        raw_payload = request.get_data()

        raw_data = (
            b"https://webhooks.danieldb.uk/webhook/appwrite/user-update" + raw_payload
        )

        expected_signature = base64.b64encode(
            hmac.new(APPWRITE_WEBHOOK_SECRET, raw_data, hashlib.sha1).digest()
        )

        try:
            if not hmac.compare_digest(expected_signature, signature.encode()):
                return jsonify({"error": "Unauthorized"}), 401
        except Exception:
            return jsonify({"error": "Comparison failed"}), 500
    else:
        logger.error(
            "No Appwrite webhook secret configured. Skipping signature verification."
        )

    try:
        payload = request.json
        logger.debug(f"Received webhook payload: {json.dumps(payload, indent=2)}")

        if payload and "$id" in payload and "name" in payload:
            user_id = payload["$id"]
            new_name = payload["name"]

            if user_id and new_name:
                redis_key = f"{CACHE_PREFIX}{user_id}"
                try:
                    redis_client.set(redis_key, new_name, ex=CACHE_TTL_SECONDS)
                    logger.info(
                        f"Updated Redis cache for user {user_id}: Name set to '{new_name}'"
                    )
                    return jsonify({"message": "Cache updated successfully"}), 200
                except Exception as e:
                    logger.error(f"Error updating Redis cache for user {user_id}: {e}")
                    return jsonify({"error": "Failed to update cache"}), 500
            else:
                logger.warning("Webhook payload missing user_id or name.")
                return jsonify({"error": "Missing user_id or name in payload"}), 400
        else:
            logger.info(
                "Webhook received, but not a relevant user name update or payload malformed."
            )
            return (
                jsonify(
                    {
                        "message": "Webhook received, no action taken for this event/payload"
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
