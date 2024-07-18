import os
import discord
from discord.utils import get
from dotenv import load_dotenv
import asyncio

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

CHANNEL_NAME = "👁︱observer"

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = discord.Client(intents=intents)
member_states = {}

@bot.event
async def on_ready():
    for guild in bot.guilds:
        await ensure_watcher_channel(guild)
        for member in guild.members:
            member_states[member.id] = {
                "avatar": member.avatar.url if member.avatar else None,
                "nickname": member.nick,
                "username": member.name
            }
    bot.loop.create_task(check_member_changes())
    print(f'Logged in as {bot.user}')

@bot.event
async def on_guild_join(guild):
    await ensure_watcher_channel(guild)
    for member in guild.members:
        member_states[member.id] = {
            "avatar": member.avatar.url if member.avatar else None,
            "nickname": member.nick,
            "username": member.name
        }

async def ensure_watcher_channel(guild):
    bot_member = guild.me
    bot_role = discord.utils.get(guild.roles, name=bot_member.name)
    bot_permissions = bot_member.guild_permissions
    print(f"Bot permissions in guild '{guild.name}': {bot_permissions}")

    watcher_channels = [channel for channel in guild.text_channels if channel.name == CHANNEL_NAME]
    
    if len(watcher_channels) > 1:
        print(f"Multiple channels named '{CHANNEL_NAME}' found in guild {guild.name} ({guild.id}). Please ensure only one exists.")
        return

    watcher_channel = watcher_channels[0] if watcher_channels else None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        bot_role: discord.PermissionOverwrite(view_channel=True)
    }

    if watcher_channel:
        bot_role_permissions = watcher_channel.permissions_for(bot_role)
        print(f"Bot role permissions in '{CHANNEL_NAME}' channel: {bot_role_permissions}")
        
        if not bot_role_permissions.view_channel:
            print(f"Attempting to update permissions for '{CHANNEL_NAME}' channel in guild {guild.name} ({guild.id})")
            try:
                await watcher_channel.set_permissions(bot_role, overwrite=overwrites[bot_role])
                print(f"Updated permissions for '{CHANNEL_NAME}' channel in guild {guild.name} ({guild.id})")
            except discord.Forbidden:
                print(f"Bot does not have permission to edit the '{CHANNEL_NAME}' channel in guild {guild.name} ({guild.id})")
        else:
            print(f"'{CHANNEL_NAME}' channel already exists with correct permissions in guild {guild.name} ({guild.id})")
    else:
        try:
            watcher_channel = await guild.create_text_channel(CHANNEL_NAME, overwrites=overwrites)
            print(f"Created '{CHANNEL_NAME}' channel in guild {guild.name} ({guild.id})")
        except discord.Forbidden:
            print(f"Bot does not have permission to create the '{CHANNEL_NAME}' channel in guild {guild.name} ({guild.id})")

async def check_member_changes():
    await bot.wait_until_ready()
    while not bot.is_closed():
        for guild in bot.guilds:
            for member in guild.members:
                if member.bot:
                    continue
                if member.id in member_states:
                    previous_state = member_states[member.id]
                    if member.avatar and previous_state["avatar"] != member.avatar.url:
                        await process_event(member, "changed their avatar", previous_state["avatar"], member.avatar.url, discord.Color.light_brown())
                        member_states[member.id]["avatar"] = member.avatar.url
                    if member.nick != previous_state["nickname"]:
                        await process_event(member, "changed their nickname", previous_state["nickname"], member.nick, discord.Color.gold())
                        member_states[member.id]["nickname"] = member.nick
                    if member.name != previous_state["username"]:
                        await process_event(member, "changed their username", previous_state["username"], member.name, discord.Color.yellow())
                        member_states[member.id]["username"] = member.name
        await asyncio.sleep(60)

async def process_event(member, action, old_value, new_value, color):
    await send_embed(
        member,
        action,
        f"**From:** {old_value}\n**To:** {new_value}",
        color
    )

async def send_embed(member, action, description, color):
    guild = member.guild
    watcher_channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
    
    if watcher_channel:
        bot_permissions = watcher_channel.permissions_for(guild.me)
        print(f"Bot permissions in '{CHANNEL_NAME}' channel: {bot_permissions}")
        
        embed = discord.Embed(color=color)
        embed.set_author(name=member.name, icon_url=member.avatar.url)
        embed.add_field(name=f"**{action}**", value=f"> {description}", inline=False)
        embed.set_footer(text=f"User ID: {member.id}")

        await watcher_channel.send(embed=embed)
        print(f"Logged {action} for {member.name}")
    else:
        print(f"'{CHANNEL_NAME}' channel not found in guild {guild.name} ({guild.id})")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    print(f"on_voice_state_update triggered for {member.name}")
    if after.channel and after.channel.name != "➕︱voice" and after.channel != before.channel:
        print(f"{member.name} joined {after.channel.name}")
        await process_event(member, "joined voice channel", None, after.channel.name, discord.Color.blue())
    
    if before.channel and before.channel.name != "➕︱voice" and after.channel != before.channel:
        print(f"{member.name} left {before.channel.name}")
        await process_event(member, "left voice channel", before.channel.name, None, discord.Color.purple())

@bot.event
async def on_member_join(member):
    if member.bot:
        return
    print(f"{member.name} joined the server {member.guild.name}")
    member_states[member.id] = {
        "avatar": member.avatar.url if member.avatar else None,
        "nickname": member.nick,
        "username": member.name
    }
    await process_event(member, "joined the server", None, None, discord.Color.green())

@bot.event
async def on_member_remove(member):
    if member.bot:
        return
    guild = member.guild
    print(f"{member.name} left the server {member.guild.name}")

    entry = await get_audit_log_entry(guild, discord.AuditLogAction.kick, member) or await get_audit_log_entry(guild, discord.AuditLogAction.ban, member)

    if entry:
        action = "was kicked" if entry.action == discord.AuditLogAction.kick else "was banned"
        await process_event(member, f"{action} from the server", None, None, discord.Color.red())
    else:
        await process_event(member, "left the server", None, None, discord.Color.red())

async def get_audit_log_entry(guild, action, member):
    async for entry in guild.audit_logs(action=action):
        if entry.target.id == member.id:
            return entry
    return None

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild:
        for attachment in message.attachments:
            if attachment.url.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp')):
                await process_event(message.author, f"sent an image in <#{message.channel.id}>", None, attachment.url, discord.Color.magenta())
            elif attachment.url.lower().endswith(('mp3', 'wav', 'ogg')):
                await process_event(message.author, f"sent a voice message in <#{message.channel.id}>", None, attachment.url, discord.Color.dark_magenta())
            else:
                await process_event(message.author, f"sent a file in <#{message.channel.id}>", None, attachment.url, discord.Color.purple())
        
        if any(link in message.content for link in ['http://', 'https://']):
            if any(domain in message.content for domain in ['tenor.com', 'giphy.com', 'imgur.com']):
                await process_event(message.author, f"sent an image in <#{message.channel.id}>", None, message.content, discord.Color.magenta())
            else:
                await process_event(message.author, f"sent a link in <#{message.channel.id}>", None, message.content, discord.Color.from_rgb(255, 182, 193))  # Light pink color

@bot.event
async def on_message_edit(before, after):
    if before.author.bot:
        return

    if before.guild:
        if before.content != after.content:
            await process_event(before.author, f"edited a message in <#{before.channel.id}>", before.content, after.content, discord.Color.orange())

bot.run(TOKEN)
