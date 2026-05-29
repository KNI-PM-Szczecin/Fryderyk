import psycopg2
from psycopg2 import pool
import logging

class Database:
    def __init__(self, db_config):
        self.db_config = db_config
        self.connection_pool = None
        self._ensure_database_exists()
        self._initialize_pool()
        if self.connection_pool:
            self._create_tables()
        else:
            print("Database: Critical error - connection pool is not initialized. Skipping table creation.")

    def _ensure_database_exists(self):
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
                        created_at TIMESTAMP,
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
                        user_id BIGINT,
                        user_name TEXT,
                        message TEXT,
                        is_edited BOOLEAN,
                        is_bot BOOLEAN DEFAULT FALSE,
                        date TIMESTAMP,
                        edit_date TIMESTAMP,
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
                        date_join TIMESTAMP,
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
                        date TIMESTAMP,
                        channel_id BIGINT,
                        channel_name TEXT,
                        guild_id BIGINT,
                        guild_name TEXT,
                        category_id BIGINT,
                        category_name TEXT
                    )
                ''')

                # Migration: Add is_bot column if it doesn't exist (for existing databases)
                cursor.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_bot BOOLEAN DEFAULT FALSE")
                cursor.execute("ALTER TABLE voice ADD COLUMN IF NOT EXISTS is_bot BOOLEAN DEFAULT FALSE")
                cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS is_bot BOOLEAN DEFAULT FALSE")

                conn.commit()
                print("Database schema initialized successfully")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error while creating tables: {error}")
            conn.rollback()
        finally:
            self.connection_pool.putconn(conn)

    def execute_query(self, query, params=None):
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
        return self.fetch_one("SELECT * FROM users WHERE user_id = %s", (user_id,))

    def delete_user(self, user_id):
        self.execute_query("DELETE FROM users WHERE user_id = %s", (user_id,))

    # --- GUILDS METHODS ---
    def put_guild(self, guild_id, guild_name):
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
        return self.fetch_one("SELECT * FROM guilds WHERE guild_id = %s", (guild_id,))

    def delete_guild(self, guild_id):
        self.execute_query("DELETE FROM guilds WHERE guild_id = %s", (guild_id,))

    # --- ROLES METHODS ---
    def put_role(self, role_id, guild_id, role_name):
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
        return self.fetch_one("SELECT * FROM roles WHERE role_id = %s", (role_id,))

    def delete_role(self, role_id):
        self.execute_query("DELETE FROM roles WHERE role_id = %s", (role_id,))

    # --- USER_ROLES METHODS ---
    def put_user_role(self, user_id, role_id):
        query = "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING"
        try:
            self.execute_query(query, (user_id, role_id))
            # Optional: very verbose, maybe skip for mass syncs
            # print(f"[DB] User {user_id} assigned role {role_id}.")
        except Exception as e:
            print(f"[DB ERR] Failed to assign role {role_id} to user {user_id}: {e}")

    def get_user_roles(self, user_id):
        return self.fetch_all("SELECT role_id FROM user_roles WHERE user_id = %s", (user_id,))

    def delete_user_role(self, user_id, role_id):
        self.execute_query("DELETE FROM user_roles WHERE user_id = %s AND role_id = %s", (user_id, role_id))

    def clear_user_roles(self, user_id):
        self.execute_query("DELETE FROM user_roles WHERE user_id = %s", (user_id,))

    # --- MESSAGES METHODS ---
    def put_message(self, user_id, user_name, message, is_edited, is_bot, date, edit_date, channel_id, channel_name, guild_id, guild_name, category_id, category_name):
        query = """
        INSERT INTO messages (user_id, user_name, message, is_edited, is_bot, date, edit_date, channel_id, channel_name, guild_id, guild_name, category_id, category_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self.execute_query(query, (user_id, user_name, message, is_edited, is_bot, date, edit_date, channel_id, channel_name, guild_id, guild_name, category_id, category_name))
            status = "edited message" if is_edited else "message"
            bot_tag = "[BOT] " if is_bot else ""
            timestamp_str = date.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp_str}] [DB] Logged {bot_tag}{status} from {user_name} in #{channel_name}.")
        except Exception as e:
            print(f"[DB ERR] Failed to log message from {user_name}: {e}")

    def get_messages(self, user_id=None, limit=100):
        if user_id:
            return self.fetch_all("SELECT * FROM messages WHERE user_id = %s ORDER BY date DESC LIMIT %s", (user_id, limit))
        return self.fetch_all("SELECT * FROM messages ORDER BY date DESC LIMIT %s", (limit,))

    def delete_message(self, message_id):
        self.execute_query("DELETE FROM messages WHERE id = %s", (message_id,))

    # --- VOICE METHODS ---
    def put_voice(self, user_id, user_name, is_bot, time_on, date_join, channel_id, channel_name, guild_id, guild_name, category_id, category_name):
        query = """
        INSERT INTO voice (user_id, user_name, is_bot, time_on, date_join, channel_id, channel_name, guild_id, guild_name, category_id, category_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self.execute_query(query, (user_id, user_name, is_bot, time_on, date_join, channel_id, channel_name, guild_id, guild_name, category_id, category_name))
            bot_tag = "[BOT] " if is_bot else ""
            timestamp_str = date_join.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp_str}] [DB] Logged {bot_tag}voice session: {user_name} spent {time_on}s in {channel_name}.")
        except Exception as e:
            print(f"[DB ERR] Failed to log voice session for {user_name}: {e}")

    def get_voice_records(self, user_id=None, limit=100):
        if user_id:
            return self.fetch_all("SELECT * FROM voice WHERE user_id = %s ORDER BY date_join DESC LIMIT %s", (user_id, limit))
        return self.fetch_all("SELECT * FROM voice ORDER BY date_join DESC LIMIT %s", (limit,))

    def delete_voice_record(self, record_id):
        self.execute_query("DELETE FROM voice WHERE id = %s", (record_id,))

    # --- EVENTS METHODS ---
    def put_event(self, user_id, user_name, is_bot, what, about, date, channel_id, channel_name, guild_id, guild_name, category_id, category_name):
        query = """
        INSERT INTO events (user_id, user_name, is_bot, what, about, date, channel_id, channel_name, guild_id, guild_name, category_id, category_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self.execute_query(query, (user_id, user_name, is_bot, what, about, date, channel_id, channel_name, guild_id, guild_name, category_id, category_name))
            user_label = user_name if user_name else "System"
            bot_tag = "[BOT] " if is_bot else ""
            timestamp_str = date.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp_str}] [DB] Logged {bot_tag}event '{what}' for {user_label}.")
        except Exception as e:
            print(f"[DB ERR] Failed to log event '{what}': {e}")

    def get_events(self, what=None, limit=100):
        if what:
            return self.fetch_all("SELECT * FROM events WHERE what = %s ORDER BY id DESC LIMIT %s", (what, limit))
        return self.fetch_all("SELECT * ORDER BY id DESC LIMIT %s", (limit,))

    def delete_event(self, event_id):
        self.execute_query("DELETE FROM events WHERE id = %s", (event_id,))
