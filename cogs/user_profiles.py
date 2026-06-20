import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption, Embed

class PodstawoweModal(nextcord.ui.Modal):
    def __init__(self, database, existing_data):
        super().__init__(
            title="Wizytówka - Podstawowe",
            custom_id="wizytowka_podstawowe_modal",
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
        
        self.plec = nextcord.ui.TextInput(
            label="Płeć",
            max_length=50,
            required=False,
            default_value=existing_data.get('plec', '') if existing_data else ''
        )
        self.add_item(self.plec)
        
        self.zaimki = nextcord.ui.TextInput(
            label="Zaimki",
            max_length=50,
            required=False,
            default_value=existing_data.get('zaimki', '') if existing_data else ''
        )
        self.add_item(self.zaimki)
        
        self.jezyk_nativ = nextcord.ui.TextInput(
            label="Język ojczysty",
            max_length=50,
            required=False,
            default_value=existing_data.get('jezyk_nativ', '') if existing_data else ''
        )
        self.add_item(self.jezyk_nativ)
        
        self.dodatkowe_jezyki = nextcord.ui.TextInput(
            label="Dodatkowe języki",
            max_length=200,
            required=False,
            default_value=existing_data.get('dodatkowe_jezyki', '') if existing_data else ''
        )
        self.add_item(self.dodatkowe_jezyki)

    async def callback(self, interaction: Interaction):
        data_to_update = {
            'nick': self.nick.value,
            'plec': self.plec.value,
            'zaimki': self.zaimki.value,
            'jezyk_nativ': self.jezyk_nativ.value,
            'dodatkowe_jezyki': self.dodatkowe_jezyki.value
        }
        # In Nextcord TextInput, empty string means not provided. 
        self.database.update_user_profile(interaction.user.id, **data_to_update)
        await interaction.send("Zaktualizowano podstawowe informacje w wizytówce!", ephemeral=True)

class ZainteresowaniaModal(nextcord.ui.Modal):
    def __init__(self, database, existing_data):
        super().__init__(
            title="Wizytówka - Zainteresowania",
            custom_id="wizytowka_zainteresowania_modal",
        )
        self.database = database
        
        self.ulubiony_kolor = nextcord.ui.TextInput(
            label="Ulubiony kolor",
            max_length=50,
            required=False,
            default_value=existing_data.get('ulubiony_kolor', '') if existing_data else ''
        )
        self.add_item(self.ulubiony_kolor)
        
        self.ulubione_zwierze = nextcord.ui.TextInput(
            label="Ulubione zwierzę",
            max_length=50,
            required=False,
            default_value=existing_data.get('ulubione_zwierze', '') if existing_data else ''
        )
        self.add_item(self.ulubione_zwierze)
        
        self.ulubiona_rzecz = nextcord.ui.TextInput(
            label="Ulubiona rzecz",
            max_length=50,
            required=False,
            default_value=existing_data.get('ulubiona_rzecz', '') if existing_data else ''
        )
        self.add_item(self.ulubiona_rzecz)
        
        self.hobby = nextcord.ui.TextInput(
            label="Hobby",
            max_length=200,
            required=False,
            default_value=existing_data.get('hobby', '') if existing_data else ''
        )
        self.add_item(self.hobby)
        
        self.notatki_usera = nextcord.ui.TextInput(
            label="Notatki",
            style=nextcord.TextInputStyle.paragraph,
            max_length=1000,
            required=False,
            default_value=existing_data.get('notatki_usera', '') if existing_data else ''
        )
        self.add_item(self.notatki_usera)

    async def callback(self, interaction: Interaction):
        data_to_update = {
            'ulubiony_kolor': self.ulubiony_kolor.value,
            'ulubione_zwierze': self.ulubione_zwierze.value,
            'ulubiona_rzecz': self.ulubiona_rzecz.value,
            'hobby': self.hobby.value,
            'notatki_usera': self.notatki_usera.value
        }
        self.database.update_user_profile(interaction.user.id, **data_to_update)
        await interaction.send("Zaktualizowano zainteresowania w wizytówce!", ephemeral=True)


class UserProfilesCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        
    def _row_to_dict(self, row):
        if not row:
            return {}
        columns = [
            'user_id', 'nick', 'plec', 'zaimki', 'ulubiony_kolor', 'ulubione_zwierze', 
            'ulubiona_rzecz', 'hobby', 'jezyk_nativ', 'dodatkowe_jezyki', 'notatki_usera', 'notatki_auto'
        ]
        return dict(zip(columns, row))

    @nextcord.slash_command(name="wizytowka", description="Zarządzanie wizytówką użytkownika")
    async def wizytowka(self, interaction: Interaction):
        pass

    @wizytowka.subcommand(name="edytuj_podstawowe", description="Edytuj podstawowe informacje (Nick, Płeć, Zaimki, Języki)")
    async def edytuj_podstawowe(self, interaction: Interaction):
        row = self.database.get_user_profile(interaction.user.id)
        existing_data = self._row_to_dict(row)
        modal = PodstawoweModal(self.database, existing_data)
        await interaction.response.send_modal(modal)

    @wizytowka.subcommand(name="edytuj_zainteresowania", description="Edytuj zainteresowania (Kolor, Zwierzę, Rzecz, Hobby, Notatki)")
    async def edytuj_zainteresowania(self, interaction: Interaction):
        row = self.database.get_user_profile(interaction.user.id)
        existing_data = self._row_to_dict(row)
        modal = ZainteresowaniaModal(self.database, existing_data)
        await interaction.response.send_modal(modal)

    @wizytowka.subcommand(name="pokaz", description="Pokaż wizytówkę swoją lub innej osoby")
    async def pokaz(self, interaction: Interaction, member: nextcord.Member = SlashOption(name="uzytkownik", description="Osoba, której wizytówkę chcesz sprawdzić", required=False)):
        target = member or interaction.user
        row = self.database.get_user_profile(target.id)
        data = self._row_to_dict(row)
        
        embed = Embed(title=f"Wizytówka: {target.display_name}", color=nextcord.Color.purple())
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)
            
        if not data:
            embed.description = "Ta osoba nie uzupełniła jeszcze swojej wizytówki."
            return await interaction.send(embed=embed)
            
        def add_field(name, key):
            val = data.get(key)
            if val and str(val).strip():
                embed.add_field(name=name, value=str(val), inline=True)
                
        # Basic
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
        
        # Notes
        val_notes = data.get("notatki_usera")
        if val_notes and str(val_notes).strip():
            embed.add_field(name="Notatki", value=str(val_notes), inline=False)
            
        await interaction.send(embed=embed)

def setup(client, config, database):
    client.add_cog(UserProfilesCog(client, config, database))
