import os
import inspect
import importlib
from dotenv import load_dotenv

class ConfigReader:
    def __init__(self):
        load_dotenv()

    def get_bot_token(self):
        return os.getenv("BOT_TOKEN", "")

    def get_db_config(self):
        return {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5432)),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "password"),
            "database": os.getenv("POSTGRES_DB", "fryderyk_db")
        }

class Loader:
    def __init__(self, payload: dict[str, any], folder="cogs"):
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
