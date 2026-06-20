# pyrefly: ignore [missing-import]
import nextcord
from nextcord.ext import commands
import random
from utilities.probability import DynamicProbability

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
    "https://tenor.com/view/freddy-freddy-fazbear-fazbear-fazbear-pizza-place-freddy-hitting-gif-5328662341160349848",
    "https://tenor.com/view/cruce-yocruce-kuudere-gif-25224185",
    "https://tenor.com/view/fire-writing-gif-25649629",
    "https://tenor.com/view/glock-gif-960828018161113653",
    "https://tenor.com/view/die-gun-shotgun-deus-vult-gif-17767114",
    "https://tenor.com/view/noted-gif-20569892",
    "https://tenor.com/view/wee-ship-cute-wave-funny-gif-16685307",
    "https://tenor.com/view/listen-here-you-little-meme-you-little-shit-damn-you-damn-it-chicken-kiev-gif-25718782",
    "https://tenor.com/view/cat-gif-26386597",
    "https://tenor.com/view/blackcat-memecat-cat-gif-18467044",
    "https://tenor.com/view/cat-light-fly-twirl-fish-gif-8400450873233434891",
    "https://tenor.com/view/vietnam-flashback-traumatized-cat-gif-7852054576948114551",
    "https://tenor.com/view/fnaf-memes-freddy-freddy-fazbear-thumbs-down-gif-14184699710270894286",
    "https://tenor.com/view/cat-gif-4693057381493629157",
    "https://tenor.com/view/kaguya-sama-love-is-war-chika-fujiwara-panic-scared-shaking-gif-17149745",
    "https://tenor.com/view/confused-white-persian-guardian-why-gif-10312546",
    "https://tenor.com/view/shrek-meme-funny-gif-15847690455777189602",
    "https://tenor.com/view/chair-chairthrow-gif-27060532",
    "https://cdn.discordapp.com/attachments/706523680666026017/1332115156788052018/pokes_you.gif",
    "https://tenor.com/view/shocked-surprised-gasp-what-cat-shock-gif-6035821429123553976",
    "https://tenor.com/view/confused-dizzy-dazed-anime-girl-gif-25919736",
    "https://tenor.com/view/gachiakuta-riyo-riyo-blinking-anime-girl-riyo-confused-riyo-shocked-gif-14301435185751912389",
    "https://tenor.com/view/jerzy-urban-tak-bylo-nie-zmy%C5%9Blam-tak-by%C5%82o-tak-by%C5%82o-nie-zmy%C5%9Blam-gif-10714281293331699150",
    "https://tenor.com/view/huh-cat-gif-17783181506241965318",
    "https://tenor.com/view/girl-anime-smile-gif-cute-gif-23970250",
    "https://tenor.com/view/wtf-cat-confused-shocked-omg-gif-15568460",
    "https://tenor.com/view/siren-borzoi-siren-dog-alarm-dog-dog-with-siren-on-head-dog-with-siren-gif-9095359937690691350",
    "https://tenor.com/view/anime-ok-okay-okey-nice-gif-8558857022530023115",
    "https://tenor.com/view/yay-yeah-happy-dance-gif-1332503735060039432",
    "https://tenor.com/view/sadcat-gif-6770984209275368356",
    "https://tenor.com/view/whizzy-imposterfox-smash-anime-smash-anime-girl-gif-21682300",
    "https://tenor.com/view/lemon-sponge-cake-cake-dessert-piece-of-cake-slice-of-cake-gif-1703523649413074288",
    "https://tenor.com/view/son-im-crine-son-im-crine-gif-5176045023480767429",
    "https://gif.fxtwitter.com/tweet_video/HFV7Wdja8AAef4b.webp",
    "https://cdn.discordapp.com/attachments/1444406575887417385/1446245946345128046/676767cap.gif",
    "https://tenor.com/view/red-paper-coach-meme-gif-11221063440541197155",
    "https://tenor.com/view/cat-funny-cat-cat-funny-cat-flashbang-flashbang-gif-8479999063609699416",
    "https://tenor.com/view/please-stop-our-brain-are-shrinking-he-hide-for-30-years-an-iq-too-high-meme-gif-8436253846885961384",
    "https://tenor.com/view/linus-torvalds-linus-nvidia-fuck-you-gif-19475186",
    "https://cdn.discordapp.com/attachments/785336580646109197/1503862363521024110/sixsayven.gif",
    "https://gif.fxtwitter.com/tweet_video/HFmQSCVakAULqnI.webp",
    "https://tenor.com/view/rip-bozo-gif-22294771",
    "https://gifconvert.vxtwitter.com/convert.avif?url=https://video.twimg.com/tweet_video/HKFV5T1W8AAjMQO.mp4",
    "https://giphy.com/gifs/big-yahu-tel-aviv-meme-scared-NLFUTRzPvI9qPOAuNW",
    "https://tenor.com/view/rozmowa-chuj-chuj-z-butem-rozmowa-chuja-z-butem-conversation-gif-12795911501748434798",
    "https://tenor.com/view/enter-gif-5985412860797742263",
    "https://tenor.com/view/dbz-perfect-cell-punching-gif-1489960437663783265",
    "https://tenor.com/view/hatsune-miku-miku-hatsune-miku-angry-not-happy-gif-10473291184535189680",
    "https://tenor.com/view/reze-tongue-out-reze-chainsaw-man-moving-her-head-reze-head-moving-reze-chainsaw-man-gif-15937294161332759512",
    "https://media.discordapp.net/attachments/772006981534744577/1029706054407303178/ezgif.com-gif-maker_-_2022-07-15T183109.613.gif?ex=6a35c63e&is=6a3474be&hm=7ff409cd43b81705fff4cb9a8f44e90affa6a816e5a57eeb2f62020121184111&",
    "https://tenor.com/view/cute-eyes-please-boba-eyes-besitoskz-sparkling-eyes-gif-11664622827672562207",
    "https://tenor.com/view/fadding-dog-traumatized-gif-10801559770686219962",
    "https://tenor.com/view/spongebob-spongebob-meme-trauma-imagination-spongebob-gif-23778560",
    "https://tenor.com/view/pips-everywhere-gif-6995441973677413110",
    "https://tenor.com/view/war-vietnam-ptsd-shell-shock-moment-gif-3022747568394546158",
    "https://tenor.com/view/maymay-entrata-marydale-smash-frying-pan-mad-gif-17894317",
    "https://tenor.com/view/spinning-the-pan-viralhog-playing-with-the-pan-turning-the-pan-gif-26489053",
    "https://tenor.com/view/lol-cats-cat-falling-gif-14250040379878929810",
    "https://tenor.com/view/cat-cat-bread-cat-loaf-cread-cat-dough-gif-15808640102646761906",
    "https://tenor.com/view/enough-gif-18442674",
    "https://tenor.com/view/trollface-gif-8242347154758580084",
    "https://tenor.com/view/sticker-yung-joc-crying-meme-man-crying-meme-thebeyonderrrr-gif-828328460466032722",
    "https://giphy.com/gifs/freddy-bite-of-87-edjstar-RvDqtHk1PP6Wvwn9k7",
    "https://giphy.com/gifs/fnaf-three-3-creepy-spring-trap-head-glitch-3lrsPjxa4dFzB0f4TE",
    "https://tenor.com/view/ashley-graves-the-coffin-of-andy-and-leyley-tcoal-gif-10201382978478232086"
]


class RandomReactionCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        
        # Initialization of dynamic probability for GIFs
        # Chances: first 1/50, after successful hit 1/75, then 1/1000 until the end of the day
        # Premium hours: from 16:00 to 22:00 for example, give 3.5x higher chance
        # Counter resets at 4:00 AM
        
        self.reaction_prob = DynamicProbability(
            base_sequence=[50, 75, 100, 150, 300, 500],
            premium_hours=[16, 17, 18, 19, 20, 21, 22],
            premium_multiplier=3.5,
            reset_hour=4,
            daily_boost_multiplier=1.5
        )

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        if message.author.bot: return
        if not message.guild: return
        if self.database.is_gif_blacklisted(message.guild.id, message.channel.id): return
        if hasattr(message.author, 'roles'):
            for role in message.author.roles:
                if self.database.is_gif_blacklisted(message.guild.id, role.id): return

        is_mentioned = self.client.user in message.mentions
        has_magic_word = "sam.uel" in message.content.lower()
        
        # --- NEW DYNAMIC PROBABILITY LOGIC ---
        extra_multiplier = 2.0 if is_mentioned else 1.0
        if has_magic_word or self.reaction_prob.should_trigger(extra_multiplier=extra_multiplier):
            gif_url = random.choice(GIF_LIST)
            await message.reply(gif_url)
