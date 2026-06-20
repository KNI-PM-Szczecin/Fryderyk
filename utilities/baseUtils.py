import os
import inspect
import importlib
from dotenv import load_dotenv

class ConfigReader:
    """
    Reads and provides configuration variables (like tokens, database credentials, 
    and n8n webhook URLs) loaded from the environment or .env file.
    """
    def __init__(self):
        """
        Initializes the configuration reader by loading environment variables via python-dotenv.
        """
        load_dotenv()

    def get_bot_token(self):
        """
        Retrieves the Discord bot token from the BOT_TOKEN environment variable.
        """
        return os.getenv("BOT_TOKEN", "")

    def get_db_config(self):
        """
        Constructs and returns a dictionary with PostgreSQL connection parameters.
        """
        return {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5432)),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "password"),
            "database": os.getenv("POSTGRES_DB", "fryderyk_db")
        }

    def get_timezone(self):
        """
        Retrieves the default timezone for the bot (defaults to Europe/Warsaw).
        """
        return os.getenv("TIMEZONE", "Europe/Warsaw")

    def get_n8n_webhook_url(self, env: str) -> str:
        """
        Retrieves the primary n8n webhook URL, dynamically choosing between production and test environments.
        """
        if env == "production":
            return os.getenv(
                "N8N_WEBHOOK_PRODUCTION_URL",
                "http://host.docker.internal:5678/webhook/b9e64b80-b5e4-4a45-9a21-55663dc072de",
            )
        return os.getenv(
            "N8N_WEBHOOK_TEST_URL",
            "http://host.docker.internal:5678/webhook-test/b9e64b80-b5e4-4a45-9a21-55663dc072de",
        )

    def get_n8n_profile_webhook_url(self, env: str) -> str:
        """
        Retrieves the n8n webhook URL specifically for the profile synchronization feature.
        """
        if env == "production":
            return os.getenv(
                "N8N_PROFILE_WEBHOOK_PRODUCTION_URL",
                "http://localhost:5678/webhook/36069440-da51-423b-8ede-acba6b17a3a7",
            )
        return os.getenv(
            "N8N_PROFILE_WEBHOOK_TEST_URL",
            "http://localhost:5678/webhook-test/36069440-da51-423b-8ede-acba6b17a3a7",
        )

    def get_n8n_speak_webhook_url(self, env: str) -> str:
        """
        Retrieves the n8n webhook URL for the 'speak up' (wypowiedz-sie) feature.
        """
        if env == "production":
            return os.getenv(
                "N8N_SPEAK_WEBHOOK_PRODUCTION_URL",
                "http://host.docker.internal:5678/webhook/wypowiedz-sie",
            )
        return os.getenv(
            "N8N_SPEAK_WEBHOOK_TEST_URL",
            "http://host.docker.internal:5678/webhook-test/wypowiedz-sie",
        )

    def get_n8n_mention_webhook_url(self, env: str) -> str:
        """
        Retrieves the n8n webhook URL used when the bot is directly mentioned.
        """
        if env == "production":
            return os.getenv(
                "N8N_MENTION_WEBHOOK_PRODUCTION_URL",
                "http://host.docker.internal:5678/webhook/fryderyk-mention",
            )
        return os.getenv(
            "N8N_MENTION_WEBHOOK_TEST_URL",
            "http://host.docker.internal:5678/webhook-test/fryderyk-mention",
        )

class Loader:
    """
    Dynamically loads Discord cog extensions from a specified folder based on their filenames 
    and matching class names, passing necessary dependencies (like database and config) to them.
    """
    def __init__(self, payload: dict[str, any], folder="cogs"):
        """
        Initializes the Loader and immediately attempts to load all valid python files 
        in the target folder as Discord cogs into the provided client.
        """
        self.payload = payload
        self.client = payload.get("client")
        self.folder = folder

        if not os.path.exists(self.folder):
            print(f"Warning: Folder {self.folder} not found.")
            return

        for filename in os.listdir(self.folder):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = f"{self.folder}.{filename[:-3]}"
                class_name = "N/A"

                base_name = filename[:-3]
                pascal_case_name = "".join(word.capitalize() for word in base_name.split("_"))
                cog_class_name = f"{pascal_case_name}Cog"
                standard_class_name = pascal_case_name

                try:
                    module = importlib.import_module(module_name)

                    if hasattr(module, cog_class_name):
                        class_name = cog_class_name
                        cog_class = getattr(module, cog_class_name)
                    elif hasattr(module, standard_class_name):
                        class_name = standard_class_name
                        cog_class = getattr(module, standard_class_name)
                    else:
                        print(f"\n > Failed to load: {module_name}: Class not found.\n")
                        continue

                    sig = inspect.signature(cog_class.__init__)
                    params = list(sig.parameters)[1:]
                    
                    args = []
                    for p in params:
                        if p in self.payload:
                            args.append(self.payload[p])
                        else:
                            print(f"Warning: Parameter '{p}' not found in payload for {class_name}")

                    cog_instance = cog_class(*args)
                    self.client.add_cog(cog_instance)
                    print(f"Loaded: {class_name}")

                except Exception as e:
                    print(f"\n > Failed to load {module_name} ({class_name}): {e}\n")

class DiscordUtils:
    """
    Contains utility functions specifically related to Discord objects and message processing.
    """
    @staticmethod
    def parse_mentions(message):
        """
        Parses Discord mentions (<@ID>, <@!ID>, <@&ID>, <#ID>) into human-readable strings.
        Used for logging to the database.
        """
        content = message.content
        if not content:
            return ""
            
        # Parse User mentions: <@123...> or <@!123...>
        for user in message.mentions:
            mention_str = f"<@{user.id}>"
            mention_str_nick = f"<@!{user.id}>"
            replacement = f"user:{user.display_name}"
            content = content.replace(mention_str, replacement).replace(mention_str_nick, replacement)
            
        # Parse Role mentions: <@&123...>
        for role in message.role_mentions:
            mention_str = f"<@&{role.id}>"
            replacement = f"role:{role.name}"
            content = content.replace(mention_str, replacement)
            
        # Parse Channel mentions: <#123...>
        for channel in message.channel_mentions:
            mention_str = f"<#{channel.id}>"
            replacement = f"channel:{channel.name}"
            content = content.replace(mention_str, replacement)
            
        return content
