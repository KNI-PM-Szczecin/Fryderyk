import psycopg2
from psycopg2 import pool
import logging

class Database:
    """
    Handles PostgreSQL database connection pooling and schema management.
    Provides methods to query and manipulate tables (users, guilds, roles, messages, voice, events, blacklists, profiles).
    """
    def __init__(self, db_config):
        """
        Initializes the Database instance.
        Validates the existence of the database, initializes a connection pool,
        and automatically runs schema migrations and table creation if needed.
        """
        self.db_config = db_config
        self.connection_pool = None
        self._ensure_database_exists()
        self._initialize_pool()
        if self.connection_pool:
            self._create_tables()
        else:
            print("Database: Critical error - connection pool is not initialized. Skipping table creation.")

    def _ensure_database_exists(self):
        """
        Ensures that the target PostgreSQL database exists.
        If it doesn't, attempts to connect to the default 'postgres' database
        and issues a CREATE DATABASE command to create it.
        """
        target_db = self.db_config.get('database')
        try:
            # Try connecting to the target database to see if it exists
            conn = psycopg2.connect(
                user=self.db_config.get('user'),
                password=self.db_config.get('password'),
                host=self.db_config.get('host'),
                port=self.db_config.get('port'),
                database=target_db
            )
            conn.close()
        except psycopg2.OperationalError as e:
            if f'database "{target_db}" does not exist' in str(e):
                print(f"Database '{target_db}' not found. Attempting to create it...")
                try:
                    # Connect to 'postgres' database to create the new one
                    conn = psycopg2.connect(
                        user=self.db_config.get('user'),
                        password=self.db_config.get('password'),
                        host=self.db_config.get('host'),
                        port=self.db_config.get('port'),
                        database='postgres'
                    )
                    conn.autocommit = True
                    with conn.cursor() as cursor:
                        cursor.execute(f'CREATE DATABASE {target_db}')
                    conn.close()
                    print(f"Database '{target_db}' created successfully.")
                except Exception as create_error:
                    print(f"Failed to create database '{target_db}': {create_error}")
            else:
                print(f"Operational error while checking database: {e}")
        except Exception as e:
            print(f"Error while checking database existence: {e}")

    def _initialize_pool(self):
        """
        Initializes a psycopg2 SimpleConnectionPool.
        Establishes a minimum of 1 and maximum of 20 concurrent connections
        using the provided database credentials.
        """
        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 20,
                user=self.db_config.get('user'),
                password=self.db_config.get('password'),
                host=self.db_config.get('host'),
                port=self.db_config.get('port'),
                database=self.db_config.get('database')
            )
            if self.connection_pool:
                print("Connection pool created successfully")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error while connecting to PostgreSQL: {error}")

    def _create_tables(self):
        """
        Creates all required tables (users, guilds, roles, messages, etc.) 
        if they do not exist. Also handles schema migrations like adding missing
        columns or changing column types (e.g., TIMESTAMP to TIMESTAMPTZ).
        """
        conn = self.connection_pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Users Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        name TEXT,
                        global_name TEXT,
                        is_bot BOOLEAN,
                        created_at TIMESTAMPTZ,
                        avatar_url TEXT,
                        banner_url TEXT,
                        public_flags INTEGER
                    )
                ''')

                # Guilds Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS guilds (
                        guild_id BIGINT PRIMARY KEY,
                        guild_name TEXT
                    )
                ''')

                # Roles Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS roles (
                        role_id BIGINT PRIMARY KEY,
                        guild_id BIGINT REFERENCES guilds(guild_id),
                        role_name TEXT
                    )
                ''')

                # User_Roles Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_roles (
                        user_id BIGINT REFERENCES users(user_id),
                        role_id BIGINT REFERENCES roles(role_id),
                        PRIMARY KEY (user_id, role_id)
                    )
                ''')

                # Messages Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        discord_id BIGINT UNIQUE,
                        user_id BIGINT,
                        user_name TEXT,
                        message TEXT,
                        is_edited BOOLEAN,
                        is_bot BOOLEAN DEFAULT FALSE,
                        date TIMESTAMPTZ,
                        edit_date TIMESTAMPTZ,
                        channel_id BIGINT,
                        channel_name TEXT,
                        guild_id BIGINT,
                        guild_name TEXT,
                        category_id BIGINT,
                        category_name TEXT
                    )
                ''')

                # Voice Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS voice (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT,
                        user_name TEXT,
                        is_bot BOOLEAN DEFAULT FALSE,
                        time_on INTEGER,
                        date_join TIMESTAMPTZ,
                        channel_id BIGINT,
                        channel_name TEXT,
                        guild_id BIGINT,
                        guild_name TEXT,
                        category_id BIGINT,
                        category_name TEXT
                    )
                ''')

                # Events Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS events (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT,
                        user_name TEXT,
                        is_bot BOOLEAN DEFAULT FALSE,
                        what TEXT,
                        about TEXT,
                        date TIMESTAMPTZ,
                        channel_id BIGINT,
                        channel_name TEXT,
                        guild_id BIGINT,
                        guild_name TEXT,
                        category_id BIGINT,
                        category_name TEXT
                    )
                ''')

                # Log Blacklist Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS log_blacklist (
                        guild_id BIGINT,
                        disabled_id BIGINT,
                        type TEXT,
                        PRIMARY KEY (guild_id, disabled_id)
                    )
                ''')

                # GIF Blacklist Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gif_blacklist (
                        guild_id BIGINT,
                        disabled_id BIGINT,
                        type TEXT,
                        PRIMARY KEY (guild_id, disabled_id)
                    )
                ''')

                # User Profiles Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                        nick TEXT,
                        plec TEXT,
                        zaimki TEXT,
                        ulubiony_kolor TEXT,
                        ulubione_zwierze TEXT,
                        ulubiona_rzecz TEXT,
                        hobby TEXT,
                        jezyk_nativ TEXT,
                        dodatkowe_jezyki TEXT,
                        notatki_usera TEXT,
                        notatki_auto TEXT,
                        technologies TEXT,
                        ulubione_gry TEXT,
                        ulubione_ksiazki TEXT,
                        ulubione_filmy TEXT
                    )
                ''')

                # Migration: Add columns if they don't exist
                cursor.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS technologies TEXT")
                cursor.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS ulubione_gry TEXT")
                cursor.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS ulubione_ksiazki TEXT")
                cursor.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS ulubione_filmy TEXT")
                cursor.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS discord_id BIGINT UNIQUE")
                cursor.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_bot BOOLEAN DEFAULT FALSE")
                cursor.execute("ALTER TABLE voice ADD COLUMN IF NOT EXISTS is_bot BOOLEAN DEFAULT FALSE")
                cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS is_bot BOOLEAN DEFAULT FALSE")

                # Migration: Remove feature column from log_blacklist if it was added
                cursor.execute('''
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='log_blacklist' AND column_name='feature') THEN
                            ALTER TABLE log_blacklist DROP CONSTRAINT IF EXISTS log_blacklist_pkey CASCADE;
                            ALTER TABLE log_blacklist DROP COLUMN feature;
                            ALTER TABLE log_blacklist ADD PRIMARY KEY (guild_id, disabled_id);
                        END IF;
                    END $$;
                ''')

                # Migration: promote legacy TIMESTAMP columns to TIMESTAMPTZ so PG
                # handles timezone conversion natively. Existing bare values are
                # interpreted as local time in the server's current TimeZone GUC
                # (the same setting under which they were originally stored).
                cursor.execute('''
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='users' AND column_name='created_at'
                                     AND data_type='timestamp without time zone') THEN
                            ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMPTZ
                                USING created_at AT TIME ZONE current_setting('TimeZone');
                        END IF;
                        IF EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='messages' AND column_name='date'
                                     AND data_type='timestamp without time zone') THEN
                            ALTER TABLE messages ALTER COLUMN date TYPE TIMESTAMPTZ
                                USING date AT TIME ZONE current_setting('TimeZone');
                        END IF;
                        IF EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='messages' AND column_name='edit_date'
                                     AND data_type='timestamp without time zone') THEN
                            ALTER TABLE messages ALTER COLUMN edit_date TYPE TIMESTAMPTZ
                                USING edit_date AT TIME ZONE current_setting('TimeZone');
                        END IF;
                        IF EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='voice' AND column_name='date_join'
                                     AND data_type='timestamp without time zone') THEN
                            ALTER TABLE voice ALTER COLUMN date_join TYPE TIMESTAMPTZ
                                USING date_join AT TIME ZONE current_setting('TimeZone');
                        END IF;
                        IF EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='events' AND column_name='date'
                                     AND data_type='timestamp without time zone') THEN
                            ALTER TABLE events ALTER COLUMN date TYPE TIMESTAMPTZ
                                USING date AT TIME ZONE current_setting('TimeZone');
                        END IF;
                    END $$;
                ''')

                conn.commit()
                print("Database schema initialized successfully")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error while creating tables: {error}")
            conn.rollback()
        finally:
            self.connection_pool.putconn(conn)

    def execute_query(self, query, params=None):
        """
        Executes a SQL query that modifies data (INSERT, UPDATE, DELETE).
        Automatically acquires a connection from the pool, commits the transaction,
        and returns the cursor upon success. Rolls back the transaction on error.
        """
        if not self.connection_pool:
            return None
        conn = self.connection_pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                conn.commit()
                return cursor
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error executing query: {error}")
            conn.rollback()
        finally:
            if self.connection_pool:
                self.connection_pool.putconn(conn)

    def fetch_one(self, query, params=None):
        """
        Executes a SELECT query and returns a single row (tuple).
        Safely acquires and releases a connection from the pool.
        """
        if not self.connection_pool:
            return None
        conn = self.connection_pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error fetching data: {error}")
        finally:
            if self.connection_pool:
                self.connection_pool.putconn(conn)

    def fetch_all(self, query, params=None):
        """
        Executes a SELECT query and returns all matching rows (list of tuples).
        Safely acquires and releases a connection from the pool.
        """
        if not self.connection_pool:
            return []
        conn = self.connection_pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error fetching data: {error}")
        finally:
            if self.connection_pool:
                self.connection_pool.putconn(conn)

    # --- USERS METHODS ---
    def put_user(self, user_id, name, global_name, is_bot, created_at, avatar_url, banner_url, public_flags):
        """
        Inserts a new user or updates an existing user's information (name, global_name, 
        avatar, banner, public_flags). Logs the sync event to the console.
        """
        query = """
        INSERT INTO users (user_id, name, global_name, is_bot, created_at, avatar_url, banner_url, public_flags)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            name = EXCLUDED.name,
            global_name = EXCLUDED.global_name,
            avatar_url = EXCLUDED.avatar_url,
            banner_url = EXCLUDED.banner_url,
            public_flags = EXCLUDED.public_flags
        """
        try:
            self.execute_query(query, (user_id, name, global_name, is_bot, created_at, avatar_url, banner_url, public_flags))
            print(f"[DB] User {name} ({user_id}) synced successfully.")
        except Exception as e:
            print(f"[DB ERR] Failed to sync user {user_id}: {e}")

    def get_user(self, user_id):
        """
        Retrieves all database fields for a specific user by their Discord ID.
        """
        return self.fetch_one("SELECT * FROM users WHERE user_id = %s", (user_id,))

    def delete_user(self, user_id):
        """
        Removes a user from the database by their Discord ID.
        """
        self.execute_query("DELETE FROM users WHERE user_id = %s", (user_id,))

    # --- USER PROFILES METHODS ---
    def update_user_profile(self, user_id, **kwargs):
        """
        Inserts or updates the extended profile details of a user (e.g., pronouns, 
        favorite colors, hobbies, known technologies). Accepts a dynamic set of fields via kwargs.
        """
        if not kwargs:
            return
        
        columns = ['user_id'] + list(kwargs.keys())
        values = [user_id] + list(kwargs.values())
        
        placeholders = ', '.join(['%s'] * len(columns))
        col_names = ', '.join(columns)
        
        updates = ', '.join([f"{k} = EXCLUDED.{k}" for k in kwargs.keys()])
        
        query = f"""
        INSERT INTO user_profiles ({col_names})
        VALUES ({placeholders})
        ON CONFLICT (user_id) DO UPDATE SET
            {updates}
        """
        
        try:
            self.execute_query(query, tuple(values))
            print(f"[DB] User profile {user_id} updated successfully.")
        except Exception as e:
            print(f"[DB ERR] Failed to update user profile {user_id}: {e}")

    def get_user_profile(self, user_id):
        """
        Retrieves the extended profile details for a specific user by their Discord ID.
        """
        return self.fetch_one("SELECT * FROM user_profiles WHERE user_id = %s", (user_id,))

    def get_all_user_profiles(self):
        """
        Retrieves the Discord IDs of all users who have an extended profile in the database.
        """
        return self.fetch_all("SELECT user_id FROM user_profiles")

    # --- GUILDS METHODS ---
    def put_guild(self, guild_id, guild_name):
        """
        Inserts a new guild or updates the name of an existing guild.
        """
        query = """
        INSERT INTO guilds (guild_id, guild_name)
        VALUES (%s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET guild_name = EXCLUDED.guild_name
        """
        try:
            self.execute_query(query, (guild_id, guild_name))
            print(f"[DB] Guild {guild_name} ({guild_id}) synced successfully.")
        except Exception as e:
            print(f"[DB ERR] Failed to sync guild {guild_id}: {e}")

    def get_guild(self, guild_id):
        """
        Retrieves guild information by its ID.
        """
        return self.fetch_one("SELECT * FROM guilds WHERE guild_id = %s", (guild_id,))

    def delete_guild(self, guild_id):
        """
        Removes a guild from the database by its ID.
        """
        self.execute_query("DELETE FROM guilds WHERE guild_id = %s", (guild_id,))

    # --- ROLES METHODS ---
    def put_role(self, role_id, guild_id, role_name):
        """
        Inserts a new role or updates the name of an existing role within a specific guild.
        """
        query = """
        INSERT INTO roles (role_id, guild_id, role_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (role_id) DO UPDATE SET role_name = EXCLUDED.role_name
        """
        try:
            self.execute_query(query, (role_id, guild_id, role_name))
            print(f"[DB] Role {role_name} ({role_id}) in guild {guild_id} synced successfully.")
        except Exception as e:
            print(f"[DB ERR] Failed to sync role {role_id}: {e}")

    def get_role(self, role_id):
        """
        Retrieves role information by its ID.
        """
        return self.fetch_one("SELECT * FROM roles WHERE role_id = %s", (role_id,))

    def delete_role(self, role_id):
        """
        Removes a role from the database by its ID.
        """
        self.execute_query("DELETE FROM roles WHERE role_id = %s", (role_id,))

    # --- USER_ROLES METHODS ---
    def put_user_role(self, user_id, role_id):
        """
        Assigns a role to a user. Ignores the operation if the user already has the role.
        """
        query = "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING"
        try:
            self.execute_query(query, (user_id, role_id))
            # Optional: very verbose, maybe skip for mass syncs
            # print(f"[DB] User {user_id} assigned role {role_id}.")
        except Exception as e:
            print(f"[DB ERR] Failed to assign role {role_id} to user {user_id}: {e}")

    def get_user_roles(self, user_id):
        """
        Retrieves a list of all role IDs assigned to a specific user.
        """
        return self.fetch_all("SELECT role_id FROM user_roles WHERE user_id = %s", (user_id,))

    def delete_user_role(self, user_id, role_id):
        """
        Unassigns a specific role from a user.
        """
        self.execute_query("DELETE FROM user_roles WHERE user_id = %s AND role_id = %s", (user_id, role_id))

    def clear_user_roles(self, user_id):
        """
        Removes all roles assigned to a specific user.
        """
        self.execute_query("DELETE FROM user_roles WHERE user_id = %s", (user_id,))

    # --- MESSAGES METHODS ---
    def put_message(self, discord_id, user_id, user_name, message, is_edited, is_bot, date, edit_date, channel_id, channel_name, guild_id, guild_name, category_id, category_name):
        """
        Inserts a new chat message into the database. If a message with the same discord_id 
        already exists, the operation is ignored.
        """
        query = """
        INSERT INTO messages (discord_id, user_id, user_name, message, is_edited, is_bot, date, edit_date, channel_id, channel_name, guild_id, guild_name, category_id, category_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (discord_id) DO NOTHING
        """
        try:
            self.execute_query(query, (discord_id, user_id, user_name, message, is_edited, is_bot, date, edit_date, channel_id, channel_name, guild_id, guild_name, category_id, category_name))
            status = "edited message" if is_edited else "message"
            bot_tag = "[BOT] " if is_bot else ""
            timestamp_str = date.strftime("%Y-%m-%d %H:%M:%S") if date else "Unknown Date"
            print(f"[{timestamp_str}] [DB] Logged {bot_tag}{status} from {user_name} in #{channel_name}.")
        except Exception as e:
            print(f"[DB ERR] Failed to log message from {user_name}: {e}")

    def get_messages(self, user_id=None, limit=100):
        """
        Retrieves the most recent messages. Can be optionally filtered by user_id and limited in count.
        """
        if user_id:
            return self.fetch_all("SELECT * FROM messages WHERE user_id = %s ORDER BY date DESC LIMIT %s", (user_id, limit))
        return self.fetch_all("SELECT * FROM messages ORDER BY date DESC LIMIT %s", (limit,))

    def message_exists(self, discord_id):
        """
        Checks if a message with the specified Discord ID already exists in the database.
        """
        if discord_id is None:
            return False
        return self.fetch_one("SELECT 1 FROM messages WHERE discord_id = %s LIMIT 1", (discord_id,)) is not None

    def delete_message(self, message_id):
        """
        Removes a message from the database using its internal database ID.
        """
        self.execute_query("DELETE FROM messages WHERE id = %s", (message_id,))

    # --- VOICE METHODS ---
    def put_voice(self, user_id, user_name, is_bot, time_on, date_join, channel_id, channel_name, guild_id, guild_name, category_id, category_name):
        """
        Logs a user's voice channel session, recording the duration (time_on) and the channel details.
        """
        query = """
        INSERT INTO voice (user_id, user_name, is_bot, time_on, date_join, channel_id, channel_name, guild_id, guild_name, category_id, category_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self.execute_query(query, (user_id, user_name, is_bot, time_on, date_join, channel_id, channel_name, guild_id, guild_name, category_id, category_name))
            bot_tag = "[BOT] " if is_bot else ""
            timestamp_str = date_join.strftime("%Y-%m-%d %H:%M:%S") if date_join else "Unknown Date"
            print(f"[{timestamp_str}] [DB] Logged {bot_tag}voice session: {user_name} spent {time_on}s in {channel_name}.")
        except Exception as e:
            print(f"[DB ERR] Failed to log voice session for {user_name}: {e}")

    def get_voice_records(self, user_id=None, limit=100):
        """
        Retrieves recent voice session records. Can be filtered by user_id and limited in count.
        """
        if user_id:
            return self.fetch_all("SELECT * FROM voice WHERE user_id = %s ORDER BY date_join DESC LIMIT %s", (user_id, limit))
        return self.fetch_all("SELECT * FROM voice ORDER BY date_join DESC LIMIT %s", (limit,))

    def delete_voice_record(self, record_id):
        """
        Removes a voice session record using its internal database ID.
        """
        self.execute_query("DELETE FROM voice WHERE id = %s", (record_id,))

    # --- EVENTS METHODS ---
    def put_event(self, user_id, user_name, is_bot, what, about, date, channel_id, channel_name, guild_id, guild_name, category_id, category_name):
        """
        Logs a generic event (e.g., user joined, member banned, role created) along with 
        its context (who, what, about) and location.
        """
        query = """
        INSERT INTO events (user_id, user_name, is_bot, what, about, date, channel_id, channel_name, guild_id, guild_name, category_id, category_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self.execute_query(query, (user_id, user_name, is_bot, what, about, date, channel_id, channel_name, guild_id, guild_name, category_id, category_name))
            user_label = user_name if user_name else "System"
            bot_tag = "[BOT] " if is_bot else ""
            timestamp_str = date.strftime("%Y-%m-%d %H:%M:%S") if date else "Unknown Date"
            print(f"[{timestamp_str}] [DB] Logged {bot_tag}event '{what}' for {user_label}.")
        except Exception as e:
            print(f"[DB ERR] Failed to log event '{what}': {e}")

    def get_events(self, what=None, limit=100):
        """
        Retrieves recent logged events. Can be filtered by the 'what' field (event type) and limited.
        """
        if what:
            return self.fetch_all("SELECT * FROM events WHERE what = %s ORDER BY id DESC LIMIT %s", (what, limit))
        return self.fetch_all("SELECT * FROM events ORDER BY id DESC LIMIT %s", (limit,))

    def delete_event(self, event_id):
        """
        Removes a specific event record using its internal database ID.
        """
        self.execute_query("DELETE FROM events WHERE id = %s", (event_id,))

    # --- BLACKLIST METHODS ---
    def put_blacklist_item(self, guild_id, disabled_id, item_type):
        """
        Adds an item (channel or role) to the event/message logging blacklist for a specific guild.
        """
        query = """
        INSERT INTO log_blacklist (guild_id, disabled_id, type)
        VALUES (%s, %s, %s)
        ON CONFLICT (guild_id, disabled_id) DO UPDATE SET type = EXCLUDED.type
        """
        try:
            self.execute_query(query, (guild_id, disabled_id, item_type))
            print(f"[DB] Blacklisted {item_type} {disabled_id} in guild {guild_id}.")
        except Exception as e:
            print(f"[DB ERR] Failed to blacklist {disabled_id}: {e}")

    def delete_blacklist_item(self, guild_id, disabled_id):
        """
        Removes an item from the event/message logging blacklist.
        """
        self.execute_query("DELETE FROM log_blacklist WHERE guild_id = %s AND disabled_id = %s", (guild_id, disabled_id))

    def is_blacklisted(self, guild_id, disabled_id):
        """
        Checks whether a specific channel or role is currently blacklisted from event/message logging.
        """
        if not guild_id or not disabled_id:
            return False
        return self.fetch_one("SELECT 1 FROM log_blacklist WHERE guild_id = %s AND disabled_id = %s LIMIT 1", (guild_id, disabled_id)) is not None

    def get_blacklist(self, guild_id):
        """
        Retrieves the complete event/message logging blacklist for a specific guild.
        """
        return self.fetch_all("SELECT disabled_id, type FROM log_blacklist WHERE guild_id = %s", (guild_id,))

    # --- GIF BLACKLIST METHODS ---
    def put_gif_blacklist_item(self, guild_id, disabled_id, item_type):
        """
        Adds an item (channel or role) to the random GIF reaction blacklist for a specific guild.
        """
        query = """
        INSERT INTO gif_blacklist (guild_id, disabled_id, type)
        VALUES (%s, %s, %s)
        ON CONFLICT (guild_id, disabled_id) DO UPDATE SET type = EXCLUDED.type
        """
        try:
            self.execute_query(query, (guild_id, disabled_id, item_type))
            print(f"[DB] GIF-Blacklisted {item_type} {disabled_id} in guild {guild_id}.")
        except Exception as e:
            print(f"[DB ERR] Failed to GIF-blacklist {disabled_id}: {e}")

    def delete_gif_blacklist_item(self, guild_id, disabled_id):
        """
        Removes an item from the random GIF reaction blacklist.
        """
        self.execute_query("DELETE FROM gif_blacklist WHERE guild_id = %s AND disabled_id = %s", (guild_id, disabled_id))

    def is_gif_blacklisted(self, guild_id, disabled_id):
        """
        Checks whether a specific channel or role is currently blacklisted from random GIF reactions.
        """
        if not guild_id or not disabled_id:
            return False
        return self.fetch_one("SELECT 1 FROM gif_blacklist WHERE guild_id = %s AND disabled_id = %s LIMIT 1", (guild_id, disabled_id)) is not None

    def get_gif_blacklist(self, guild_id):
        """
        Retrieves the complete random GIF reaction blacklist for a specific guild.
        """
        return self.fetch_all("SELECT disabled_id, type FROM gif_blacklist WHERE guild_id = %s", (guild_id,))
