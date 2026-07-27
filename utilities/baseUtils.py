import os
import inspect
import importlib
import aiohttp
from dotenv import load_dotenv


def get_operator_role_name() -> str:
    """
    Name of the role required to use ANY of the bot's slash commands (enforced by
    a global application command check in main.py and by /off's explicit check).
    Matching by name instead of ID means the same build works on every guild —
    each server just needs a role with this name. Configurable via the
    OPERATOR_ROLE_NAME env var. Must be called after load_dotenv() has run (i.e.
    after ConfigReader is constructed), not at import time of this module.
    """
    return os.getenv("OPERATOR_ROLE_NAME", "fryderyk-operator")


def normalize_role_name(name: str) -> str:
    """
    Reduces a role name to a comparable form: lowercase, letters/digits only.
    So "fryderyk-operator", "Fryderyk Operator" and "Fryderyk_Operator" all
    match — guilds rarely name the role identically, and a case/separator
    mismatch would silently lock everyone out of every command.
    """
    return "".join(ch for ch in name.casefold() if ch.isalnum())


def is_operator(interaction) -> bool:
    """
    True if the interaction's author has the operator role (matched by name via
    normalize_role_name). False outside guilds, where the user has no roles.
    """
    wanted = normalize_role_name(get_operator_role_name())
    roles = getattr(interaction.user, "roles", None) or []
    return any(normalize_role_name(role.name) == wanted for role in roles)


async def post_webhook(url: str, payload: dict) -> int:
    """
    POSTs a JSON payload to a webhook URL and returns the HTTP status code.
    Network errors propagate to the caller (aiohttp exceptions).
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            return resp.status

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
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "password"),
            "database": os.getenv("POSTGRES_DB", "fryderyk_db")
        }

    def get_timezone(self):
        """
        Retrieves the default timezone for the bot (defaults to Europe/Warsaw).
        """
        return os.getenv("TIMEZONE", "Europe/Warsaw")

    # feature -> (env var prefix, default host, webhook path)
    # Env var names stay as before: <PREFIX>_PRODUCTION_URL / <PREFIX>_TEST_URL.
    _N8N_WEBHOOKS = {
        "summarize": ("N8N_WEBHOOK", "http://host.docker.internal:5678", "b9e64b80-b5e4-4a45-9a21-55663dc072de"),
        "profile": ("N8N_PROFILE_WEBHOOK", "http://localhost:5678", "36069440-da51-423b-8ede-acba6b17a3a7"),
        "speak": ("N8N_SPEAK_WEBHOOK", "http://host.docker.internal:5678", "wypowiedz-sie"),
        "mention": ("N8N_MENTION_WEBHOOK", "http://host.docker.internal:5678", "fryderyk-mention"),
    }

    def get_n8n_url(self, feature: str, env: str) -> str:
        """
        Retrieves the n8n webhook URL for the given feature ('summarize', 'profile',
        'speak', 'mention') and environment ('production' or 'test').
        """
        env_prefix, default_host, path = self._N8N_WEBHOOKS[feature]
        if env == "production":
            return os.getenv(f"{env_prefix}_PRODUCTION_URL", f"{default_host}/webhook/{path}")
        return os.getenv(f"{env_prefix}_TEST_URL", f"{default_host}/webhook-test/{path}")

    def get_n8n_mention_envs(self) -> list[str]:
        """
        Environments the mention webhook fires to, from the comma-separated
        N8N_MENTION_ENVS variable (default: production only).
        """
        raw = os.getenv("N8N_MENTION_ENVS", "production")
        return [e.strip() for e in raw.split(",") if e.strip()]

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
    # File extensions treated as images/GIFs when an attachment lacks a usable MIME type.
    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".gifv", ".webp", ".bmp", ".tiff", ".apng")

    @staticmethod
    def extract_media_urls(message):
        """
        Collects URLs of images and GIFs attached to or embedded in a message.
        Only the links are gathered — no blobs are downloaded. Covers uploaded
        image/GIF attachments (matched by MIME type or file extension) as well as
        image/GIF embeds such as Tenor and Giphy links.
        Returns a list of unique URLs (possibly empty).
        """
        urls = []

        def _add(url):
            if url and url not in urls:
                urls.append(url)

        # Uploaded files: keep only images/GIFs, identified by MIME type or extension.
        for attachment in message.attachments:
            content_type = (attachment.content_type or "").lower()
            filename = (attachment.filename or "").lower()
            if content_type.startswith("image/") or filename.endswith(DiscordUtils.IMAGE_EXTENSIONS):
                _add(attachment.url)

        # Embeds: image embeds and animated GIF embeds (Tenor, Giphy, direct links).
        # The image/thumbnail/video proxies always exist; their .url is None when unset.
        for embed in message.embeds:
            if embed.type in ("image", "gifv"):
                _add(embed.url)
                _add(embed.video.url)
            _add(embed.image.url)
            _add(embed.thumbnail.url)

        return urls

    @staticmethod
    def parse_mentions(message):
        """
        Wrapper that returns the message content with mentions made human-readable
        and any image/GIF links appended inline (so the logged text reads like
        "siemka <link>"). Links already present in the text are not duplicated.
        """
        content = DiscordUtils._parse_mentions_text(message)

        extra_links = [
            url for url in DiscordUtils.extract_media_urls(message)
            if url not in content
        ]
        if extra_links:
            content = "\n".join([content, *extra_links]).strip()

        return content

    @staticmethod
    def _parse_mentions_text(message):
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
