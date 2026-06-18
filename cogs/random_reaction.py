import nextcord
from nextcord.ext import commands
import random

GIF_LIST = [
    "https://tenor.com/view/freddy-fazbear-rock-eyebrow-fnaf-gif-6454127445528826902",
    "https://tenor.com/view/freddy-meme-fnaf-2-fnaf-movie-2-fnaf-2-movie-freddy-fazbear-gif-5644415851310933669",
    "https://tenor.com/view/mad-angry-freddy-fazbear-fnaf-fnaf-2-gif-16104788145259250749",
    "https://tenor.com/view/fnaf-fnaf-memes-freddy-five-nights-at-freddys-nuh-uh-gif-27238996",
    "https://tenor.com/view/silvagunner-fnaf-freddy-fazbear-five-nights-at-freddy%27s-dancing-gif-14762630636955132218",
    "https://tenor.com/view/happy-birthday-gif-17660082845475259319",
    "https://tenor.com/view/fnaf-2-movie-fnaf-five-nights-at-freddy%27s-fnaf-2-five-nights-at-freddy%27s-2-gif-12369179100694276775",
    "https://tenor.com/view/fnaf-freddy-fazbear-fazball-stare-gif-1639277911672072390",
    "https://tenor.com/view/fnaf-five-nights-at-freddies-twerk-qurky-quirky-gif-22598252",
    "https://tenor.com/view/freddy-fazbear-freddy-fazbear-gif-2848699463235821303",
    "https://tenor.com/view/freddy-fazbear-thinking-freddy-fazbear-ishowspeed-freddy-thinking-fnaf-gif-17257291184050247880",
    "https://tenor.com/view/freddy-fazbear-five-nights-at-freddy%27s-laugh-meme-funny-gif-2116053108138318954",
    "https://tenor.com/view/wedsus123-gif-12135227489476844190",
    "https://tenor.com/view/fnaf-five-nights-at-freddy%27s-fnaf-cosplay-glamrock-freddy-freddy-gif-8108475152790362158",
    "https://tenor.com/view/fnaf-jumpscare-gif-15241987753394250264",
    "https://tenor.com/view/five-nights-at-freddy%27s-fazbear-scary-freddy-real-gif-16745659071119474615",
    "https://tenor.com/view/meme-fnaf-freddy-five-nights-at-freddy-five-nights-at-freddys-gif-9125253900155678100",
    "https://tenor.com/view/freddy-fazbear-fnaf-five-nights-at-freddy%27s-gif-15838626481770486913",
    "https://tenor.com/view/fnaf-freddy-gif-25757699",
    "https://tenor.com/view/freddy-fazbear-freddy-shield-banging-fnaf-memes-withered-freddy-skeleton-shield-gif-11389322723981596598",
    "https://tenor.com/view/golden-freddy-dan%C3%A7ando-gif-1331357974706780990",
    "https://tenor.com/view/freddy-mewing-gif-16618854983432963802",
    "https://tenor.com/view/fnaf-fnaf-memes-freddy-fazbear-freddy-freaky-gif-12693495263874297725",
    "https://tenor.com/view/freddy-freddy-fazbear-fnaf-surprise-bear-gif-10797545912537514262",
    "https://tenor.com/view/toy-bonnie-gif-101708507110185553",
    "https://tenor.com/view/freddy-fazbear-scratch-sml-itchy-fnaf-gif-18275413323837981137",
    "https://tenor.com/view/freddy-freddy-fazbear-dance-dancing-goofy-ahh-gif-11464344684174536774",
    "https://tenor.com/view/freddy-freddy-fazbear-fazbear-fazbear-pizza-place-freddy-hitting-gif-5328662341160349848"
]

class RandomReactionCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        if message.author.bot: return
        if not message.guild: return
        if self.database.is_gif_blacklisted(message.guild.id, message.channel.id): return
        if hasattr(message.author, 'roles'):
            for role in message.author.roles:
                if self.database.is_gif_blacklisted(message.guild.id, role.id): return

        is_mentioned = self.client.user in message.mentions
        chance = 10 if is_mentioned else 500

        if random.randint(1, chance) == 1:
            gif_url = random.choice(GIF_LIST)
            await message.reply(gif_url)
