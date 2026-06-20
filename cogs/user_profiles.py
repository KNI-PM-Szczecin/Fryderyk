import re
import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption, Embed

class BasicInfoModal(nextcord.ui.Modal):
    """
    A Discord UI Modal form for collecting and updating a user's basic profile information
    such as nickname, gender, pronouns, and languages.
    """
    def __init__(self, database, existing_data):
        """
        Initializes the basic info modal, pre-filling fields with existing data from the database.
        """
        super().__init__(
            title="Wizytówka - Podstawowe",
            custom_id="user_profile_basic_modal",
        )
        self.database = database
        
        self.nick = nextcord.ui.TextInput(
            label="Nick",
            min_length=1,
            max_length=50,
            required=False,
            default_value=existing_data.get('nick', '') if existing_data else ''
        )
        self.add_item(self.nick)
        
        self.gender = nextcord.ui.TextInput(
            label="Płeć",
            max_length=50,
            required=False,
            default_value=existing_data.get('plec', '') if existing_data else ''
        )
        self.add_item(self.gender)
        
        self.pronouns = nextcord.ui.TextInput(
            label="Zaimki",
            max_length=50,
            required=False,
            default_value=existing_data.get('zaimki', '') if existing_data else ''
        )
        self.add_item(self.pronouns)
        
        self.native_language = nextcord.ui.TextInput(
            label="Język ojczysty",
            max_length=50,
            required=False,
            default_value=existing_data.get('jezyk_nativ', '') if existing_data else ''
        )
        self.add_item(self.native_language)
        
        self.additional_languages = nextcord.ui.TextInput(
            label="Dodatkowe języki",
            max_length=200,
            required=False,
            default_value=existing_data.get('dodatkowe_jezyki', '') if existing_data else ''
        )
        self.add_item(self.additional_languages)

    async def callback(self, interaction: Interaction):
        """
        Callback executed when the user submits the basic info modal.
        Saves the form data to the database and sends a confirmation message.
        """
        data_to_update = {
            'nick': self.nick.value,
            'plec': self.gender.value,
            'zaimki': self.pronouns.value,
            'jezyk_nativ': self.native_language.value,
            'dodatkowe_jezyki': self.additional_languages.value
        }
        # In Nextcord TextInput, an empty string means the field was not provided.
        self.database.update_user_profile(interaction.user.id, **data_to_update)
        await interaction.send("Zaktualizowano podstawowe informacje w wizytówce!", ephemeral=True)


class InterestsModal(nextcord.ui.Modal):
    """
    A Discord UI Modal form for collecting and updating a user's general interests
    such as favorite color, animal, thing, hobbies, and personal notes.
    """
    def __init__(self, database, existing_data):
        """
        Initializes the interests modal, pre-filling fields with existing data from the database.
        """
        super().__init__(
            title="Wizytówka - Zainteresowania",
            custom_id="user_profile_interests_modal",
        )
        self.database = database
        
        self.favorite_color = nextcord.ui.TextInput(
            label="Ulubiony kolor",
            max_length=50,
            required=False,
            default_value=existing_data.get('ulubiony_kolor', '') if existing_data else ''
        )
        self.add_item(self.favorite_color)
        
        self.favorite_animal = nextcord.ui.TextInput(
            label="Ulubione zwierzę",
            max_length=50,
            required=False,
            default_value=existing_data.get('ulubione_zwierze', '') if existing_data else ''
        )
        self.add_item(self.favorite_animal)
        
        self.favorite_thing = nextcord.ui.TextInput(
            label="Ulubiona rzecz",
            max_length=50,
            required=False,
            default_value=existing_data.get('ulubiona_rzecz', '') if existing_data else ''
        )
        self.add_item(self.favorite_thing)
        
        self.hobby = nextcord.ui.TextInput(
            label="Hobby",
            max_length=200,
            required=False,
            default_value=existing_data.get('hobby', '') if existing_data else ''
        )
        self.add_item(self.hobby)
        
        self.user_notes = nextcord.ui.TextInput(
            label="Notatki",
            style=nextcord.TextInputStyle.paragraph,
            max_length=1000,
            required=False,
            default_value=existing_data.get('notatki_usera', '') if existing_data else ''
        )
        self.add_item(self.user_notes)

    async def callback(self, interaction: Interaction):
        """
        Callback executed when the user submits the interests modal.
        Saves the form data to the database and sends a confirmation message.
        """
        data_to_update = {
            'ulubiony_kolor': self.favorite_color.value,
            'ulubione_zwierze': self.favorite_animal.value,
            'ulubiona_rzecz': self.favorite_thing.value,
            'hobby': self.hobby.value,
            'notatki_usera': self.user_notes.value
        }
        self.database.update_user_profile(interaction.user.id, **data_to_update)
        await interaction.send("Zaktualizowano zainteresowania w wizytówce!", ephemeral=True)


class Interests2Modal(nextcord.ui.Modal):
    """
    A Discord UI Modal form for collecting and updating a user's specific media interests
    such as favorite games, books, movies, and known technologies.
    """
    def __init__(self, database, existing_data):
        """
        Initializes the second interests modal, pre-filling fields with existing data from the database.
        """
        super().__init__(
            title="Wizytówka - Zainteresowania 2",
            custom_id="user_profile_interests2_modal",
        )
        self.database = database
        
        self.technologies = nextcord.ui.TextInput(
            label="Technologie (np. Python, C++)",
            style=nextcord.TextInputStyle.paragraph,
            max_length=500,
            required=False,
            default_value=existing_data.get('technologies', '') if existing_data else ''
        )
        self.add_item(self.technologies)

        self.games = nextcord.ui.TextInput(
            label="Ulubione gry",
            max_length=200,
            required=False,
            default_value=existing_data.get('ulubione_gry', '') if existing_data else ''
        )
        self.add_item(self.games)
        
        self.books = nextcord.ui.TextInput(
            label="Ulubione książki",
            max_length=200,
            required=False,
            default_value=existing_data.get('ulubione_ksiazki', '') if existing_data else ''
        )
        self.add_item(self.books)
        
        self.movies = nextcord.ui.TextInput(
            label="Ulubione filmy/seriale",
            max_length=200,
            required=False,
            default_value=existing_data.get('ulubione_filmy', '') if existing_data else ''
        )
        self.add_item(self.movies)

    async def callback(self, interaction: Interaction):
        """
        Callback executed when the user submits the second interests modal.
        Saves the form data to the database and sends a confirmation message.
        """
        data_to_update = {
            'technologies': self.technologies.value,
            'ulubione_gry': self.games.value,
            'ulubione_ksiazki': self.books.value,
            'ulubione_filmy': self.movies.value
        }
        self.database.update_user_profile(interaction.user.id, **data_to_update)
        await interaction.send("Zaktualizowano dodatkowe zainteresowania w wizytówce!", ephemeral=True)


class UserProfilesCog(commands.Cog):
    """
    Discord Cog responsible for managing the user profiles (wizytówka) system.
    Provides slash commands to display profiles and launch interactive Modals 
    for users to edit their own profile data.
    """
    def __init__(self, client, config, database):
        """
        Initializes the UserProfilesCog with the bot instance, config, and database connection.
        """
        self.client = client
        self.config = config
        self.database = database
        
    def _row_to_dict(self, row):
        """Convert a database row into a dictionary for easier access."""
        if not row:
            return {}
        columns = [
            'user_id', 'nick', 'plec', 'zaimki', 'ulubiony_kolor', 'ulubione_zwierze', 
            'ulubiona_rzecz', 'hobby', 'jezyk_nativ', 'dodatkowe_jezyki', 'notatki_usera', 'notatki_auto',
            'technologies', 'ulubione_gry', 'ulubione_ksiazki', 'ulubione_filmy'
        ]
        return dict(zip(columns, row))

    @nextcord.slash_command(name="wizytowka", description="Zarządzanie wizytówką użytkownika")
    async def user_profile(self, interaction: Interaction):
        """Base command for the user profile (wizytówka) feature."""
        pass

    @user_profile.subcommand(name="edytuj_podstawowe", description="Edytuj podstawowe informacje (Nick, Płeć, Zaimki, Języki)")
    async def edit_basic_info(self, interaction: Interaction):
        """Open a modal to edit basic profile information."""
        row = self.database.get_user_profile(interaction.user.id)
        existing_data = self._row_to_dict(row)
        modal = BasicInfoModal(self.database, existing_data)
        await interaction.response.send_modal(modal)

    @user_profile.subcommand(name="edytuj_zainteresowania", description="Edytuj zainteresowania (Kolor, Zwierzę, Rzecz, Hobby, Notatki)")
    async def edit_interests(self, interaction: Interaction):
        """Open a modal to edit profile interests."""
        row = self.database.get_user_profile(interaction.user.id)
        existing_data = self._row_to_dict(row)
        modal = InterestsModal(self.database, existing_data)
        await interaction.response.send_modal(modal)

    @user_profile.subcommand(name="edytuj_zainteresowania2", description="Edytuj dodatkowe zainteresowania (Gry, Książki, Filmy, Technologie)")
    async def edit_interests2(self, interaction: Interaction):
        """Open a modal to edit additional interests (technologies, games, books, movies)."""
        row = self.database.get_user_profile(interaction.user.id)
        existing_data = self._row_to_dict(row)
        modal = Interests2Modal(self.database, existing_data)
        await interaction.response.send_modal(modal)

    @user_profile.subcommand(name="pokaz", description="Pokaż wizytówkę swoją lub innej osoby")
    async def show_profile(self, interaction: Interaction, member: nextcord.Member = SlashOption(name="uzytkownik", description="Osoba, której wizytówkę chcesz sprawdzić", required=False)):
        """Show the specified user's profile, or the caller's profile if no user is specified."""
        target = member or interaction.user
        row = self.database.get_user_profile(target.id)
        data = self._row_to_dict(row)
        
        embed_color = nextcord.Color.purple()
        if data and data.get("ulubiony_kolor"):
            color_str = str(data["ulubiony_kolor"]).strip()
            # Match formats like #ff00ff, ff00ff, 0xff00ff anywhere in the text
            match = re.search(r'(?:^|[^a-zA-Z0-9_])(?:#|0x)?([0-9a-fA-F]{6})(?=[^a-zA-Z0-9_]|$)', color_str)
            if match:
                embed_color = nextcord.Color(int(match.group(1), 16))
                
        embed = Embed(title=f"Wizytówka: {target.display_name}", color=embed_color)
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)
            
        if not data:
            embed.description = "Ta osoba nie uzupełniła jeszcze swojej wizytówki."
            return await interaction.send(embed=embed)
            
        def add_field(name, key):
            """
            Helper function to safely add a field to the embed only if the value exists 
            and is not entirely whitespace.
            """
            val = data.get(key)
            if val and str(val).strip():
                embed.add_field(name=name, value=str(val), inline=True)
                
        # Basic Information
        add_field("Nick", "nick")
        add_field("Płeć", "plec")
        add_field("Zaimki", "zaimki")
        add_field("Język ojczysty", "jezyk_nativ")
        add_field("Dodatkowe języki", "dodatkowe_jezyki")
        
        # Interests
        add_field("Ulubiony kolor", "ulubiony_kolor")
        add_field("Ulubione zwierzę", "ulubione_zwierze")
        add_field("Ulubiona rzecz", "ulubiona_rzecz")
        add_field("Hobby", "hobby")
        
        add_field("Ulubione gry", "ulubione_gry")
        add_field("Ulubione książki", "ulubione_ksiazki")
        add_field("Ulubione filmy/seriale", "ulubione_filmy")
        
        # Skills
        add_field("Technologie (np. Python)", "technologies")
        
        # User Notes
        val_notes = data.get("notatki_usera")
        if val_notes and str(val_notes).strip():
            embed.add_field(name="Notatki", value=str(val_notes), inline=False)
            
        await interaction.send(embed=embed)

    @nextcord.slash_command(name="wizytowki_lista", description="Pokaż kto ma uzupełnioną wizytówkę", default_member_permissions=nextcord.Permissions(administrator=True))
    async def list_filled_profiles(self, interaction: Interaction):
        """Show a list of users who have a profile in the database."""
        rows = self.database.get_all_user_profiles()
        if not rows:
            return await interaction.send("Nikt jeszcze nie uzupełnił wizytówki.", ephemeral=True)
            
        user_ids = [row[0] for row in rows]
        mentions = [f"<@{uid}>" for uid in user_ids]
        
        description = "\n".join(mentions)
        if len(description) > 4000:
            description = description[:4000] + "\n...i więcej."
            
        embed = Embed(title="Uzupełnione wizytówki", description=description, color=nextcord.Color.green())
        embed.set_footer(text=f"Łącznie: {len(user_ids)} osób")
        
        await interaction.send(embed=embed, ephemeral=True)

def setup(client, config, database):
    """
    Extension setup function required by nextcord to load the cog automatically.
    """
    client.add_cog(UserProfilesCog(client, config, database))
