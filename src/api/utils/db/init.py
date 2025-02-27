async def init_db(db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_users (
                id SERIAL PRIMARY KEY,
                blocker_id TEXT NOT NULL,
                blocked_id TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(blocker_id, blocked_id)
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS friend_requests (
                id SERIAL PRIMARY KEY,
                sender_id TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                status TEXT CHECK(status IN ('pending', 'accepted', 'declined')) DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sender_id, receiver_id)
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_pics (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                UNIQUE(user_id)
            )
            """
        )

        # Remove duplicate friend requests
        await conn.execute(
            """
            DELETE FROM friend_requests
            WHERE id IN (
                SELECT f1.id
                FROM friend_requests f1
                JOIN friend_requests f2
                ON LOWER(f1.sender_id) = LOWER(f2.receiver_id)
                AND LOWER(f1.receiver_id) = LOWER(f2.sender_id)
                WHERE f1.id < f2.id
            )
            """
        )
        print("Reversed duplicate records removed.")

        # Update sender_id and receiver_id to lowercase
        await conn.execute(
            """
            UPDATE friend_requests
            SET sender_id = LOWER(sender_id),
                receiver_id = LOWER(receiver_id)
            """
        )

        # Set up the timetables table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timetables (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                timetable JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
            """
        )

        # New in v1.3.0 - timetable association table to link a user id (string) to a timetable url (string)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timetable_associations (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
            """
        )

        # Bus subscriptions
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bus (
                bus_id TEXT PRIMARY KEY,
                bus_bay TEXT NOT NULL DEFAULT '0'
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extra_bus_subscriptions (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL ,
                bus TEXT NOT NULL DEFAULT '',
                UNIQUE(user_id, bus)
            )
            """
        )
