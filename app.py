import json
from flask import Flask, request, jsonify, g
import sqlite3
from functools import wraps
import os
from datetime import datetime
import dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from appwrite.client import Client
from appwrite.services.account import Account
from appwrite.services.users import Users
from bus_worker import main as worker_main
from threading import Thread

dotenv.load_dotenv()

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app)

DATABASE = "data/friends.db"
TIMETABLE_DATABASE = "data/timetables.db"
BUS_DATABASE = "data/bus.db"

# Initialize Appwrite client
client = Client()
client.set_endpoint(os.getenv("APPWRITE_ENDPOINT"))
client.set_project(os.getenv("APPWRITE_PROJECT_ID"))


def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                status TEXT CHECK(status IN ('pending', 'accepted', 'declined')) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sender_id, receiver_id)
            )
        """
        )


def verify_token(token):
    """Verify Appwrite JWT token and extract user ID from itt"""
    try:
        client.set_jwt(token)
        account = Account(client)
        user = account.get()
        return user.get("$id")  # Extract user ID
    except Exception as e:
        app.logger.error(f"Token verification failed: {e}")
        return None


def get_db():
    """Reuse database connection during request lifetime."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_timetable_db():
    with sqlite3.connect(TIMETABLE_DATABASE) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timetables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timetable JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
            """
        )


def get_timetable_db():
    """Reuse timetable database connection during request lifetime."""
    if "timetable_db" not in g:
        g.timetable_db = sqlite3.connect(TIMETABLE_DATABASE)
        g.timetable_db.row_factory = sqlite3.Row
    return g.timetable_db


def get_bus_db():
    """Also reuse bus database connection during request lifetime - wow such efficiency!"""
    if "bus_db" not in g:
        g.bus_db = sqlite3.connect(BUS_DATABASE)
        g.bus_db.row_factory = sqlite3.Row
    return g.bus_db


@app.teardown_appcontext
def close_db(exception):
    """Close database connection at the end of the request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.teardown_appcontext
def close_timetable_db(exception):
    """Close timetable database connection at the end of the request."""
    timetable_db = g.pop("timetable_db", None)
    if timetable_db is not None:
        timetable_db.close()


def authenticate(f):
    """Decorator for authenticating users with their JWT from appwrite we pass using the Authorization header in requestsfrom the flutter app"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401

        token = auth_header.split(" ")[1]
        user_id = verify_token(token)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        request.user_id = user_id
        return f(*args, **kwargs)

    return decorated_function


"""
**Friend Request Routes**

The following routes are used to send, receive, and handle friend requests between users, using SQLite to store this data.
"""


@app.route("/api/friend-requests", methods=["POST"])
@authenticate
@limiter.limit("5/minute")
def send_friend_request():
    receiver_id = request.json.get("receiver_id")
    if not receiver_id:
        return jsonify({"error": "receiver_id is required"}), 400

    if receiver_id == request.user_id:
        return jsonify({"error": "Cannot send friend request to yourself"}), 400

    try:
        adminClient = Client()
        adminClient.set_endpoint(os.getenv("APPWRITE_ENDPOINT"))
        adminClient.set_project(os.getenv("APPWRITE_PROJECT_ID"))
        adminClient.set_key(os.getenv("APPWRITE_API_KEY"))
        users = Users(adminClient)
        users.get(receiver_id)
    except Exception as e:
        return jsonify({"error": "Invalid receiver_id"}), 400

    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO friend_requests (sender_id, receiver_id) VALUES (?, ?)",
                (request.user_id, receiver_id),
            )
            db.commit()
        return jsonify({"message": "Friend request sent"}), 201
    except sqlite3.IntegrityError as e:
        app.logger.error(f"Database integrity error: {e}")
        return jsonify({"error": "Friend request already exists"}), 409


@app.route("/api/friend-requests", methods=["GET"])
@authenticate
# @limiter.limit("10/minute") <- This gets called by the sidebar to check for new friend requests pretty often
def get_friend_requests():
    status = request.args.get("status", "pending")

    with get_db() as db:
        requests = db.execute(
            """SELECT * FROM friend_requests 
               WHERE receiver_id = ? AND status = ?""",
            (request.user_id, status),
        ).fetchall()

    return jsonify([dict(req) for req in requests])


@app.route("/api/friend-requests/<int:request_id>", methods=["PUT"])
@authenticate
@limiter.limit("5/minute")
def handle_friend_request(request_id):
    action = request.json.get("action")
    if action not in ["accept", "decline"]:
        return jsonify({"error": "Invalid action"}), 400

    with get_db() as db:
        req = db.execute(
            "SELECT * FROM friend_requests WHERE id = ?", (request_id,)
        ).fetchone()

        if not req:
            return jsonify({"error": "Friend request not found"}), 404

        if req["receiver_id"] != request.user_id:
            return jsonify({"error": "Unauthorized"}), 403

        if req["status"] != "pending":
            return jsonify({"error": "Request already handled"}), 400

        db.execute(
            """UPDATE friend_requests 
               SET status = ?, updated_at = ? 
               WHERE id = ?""",
            (action + "ed", datetime.now(), request_id),
        )
        db.commit()

    return jsonify({"message": f"Friend request {action}ed"})


@app.route("/api/friends", methods=["GET"])
@authenticate
@limiter.limit("25/minute")
def get_friends():
    with get_db() as db:
        friends = db.execute(
            """SELECT * FROM friend_requests 
               WHERE (sender_id = ? OR receiver_id = ?) AND status = 'accepted'""",
            (request.user_id, request.user_id),
        ).fetchall()

    return jsonify([dict(friend) for friend in friends])


"""
**Timetable Routes**

The following routes are used to upload and retrieve timetables for users. The timetable is stored in a separate database to keep the main database clean and to allow for easier scaling in the future if necessary :)
"""


@app.route("/api/timetable", methods=["POST"])
@authenticate
@limiter.limit("5/minute")
def upload_timetable():
    timetable = request.json.get("timetable")
    if not timetable:
        return jsonify({"error": "Timetable JSON is required"}), 400

    try:
        with get_timetable_db() as db:
            db.execute(
                """INSERT INTO timetables (user_id, timetable) 
                   VALUES (?, ?) 
                   ON CONFLICT(user_id) 
                   DO UPDATE SET timetable = excluded.timetable, updated_at = CURRENT_TIMESTAMP""",
                (request.user_id, json.dumps(timetable)),
            )
            db.commit()
        return jsonify({"message": "Timetable uploaded successfully"}), 201
    except sqlite3.Error as e:
        app.logger.error(f"Error uploading timetable: {e}")
        return jsonify({"error": "Failed to upload timetable"}), 500


@app.route("/api/timetable", methods=["GET"])
@authenticate
@limiter.limit("30/minute")  # Higher limit as this is called by the timetable page
def get_timetable():
    user_id = request.args.get("user_id", request.user_id)

    # Check if the user_id parameter is the requester (or a friend as that's fine too)
    if user_id != request.user_id:
        with get_db() as db:
            friendship = db.execute(
                """SELECT * FROM friend_requests 
                   WHERE status = 'accepted' 
                   AND ((sender_id = ? AND receiver_id = ?) 
                        OR (sender_id = ? AND receiver_id = ?))""",
                (request.user_id, user_id, user_id, request.user_id),
            ).fetchone()
            if not friendship:
                return jsonify({"error": "Unauthorized access"}), 403

    with get_timetable_db() as db:
        timetable = db.execute(
            "SELECT timetable FROM timetables WHERE user_id = ?", (user_id,)
        ).fetchone()

    if not timetable:
        return jsonify({"error": "Timetable not found"}), 404

    return jsonify({"timetable": json.loads(timetable["timetable"])})


@app.route("/api/bus", methods=["GET"])
@authenticate
@limiter.limit("20/minute")
def get_bus():
    with get_bus_db() as db:
        buses = db.execute("SELECT * FROM bus").fetchall()
    return jsonify([dict(bus) for bus in buses])


if __name__ == "__main__":
    init_db()
    init_timetable_db()
    # Also run main() from bus_worker.py here as a thread in the background
    worker_thread = Thread(target=worker_main)
    worker_thread.start()
    app.run(debug=False)
