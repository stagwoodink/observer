import discord
from discord.ext import commands
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import re
from datetime import datetime

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

# MongoDB setup
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db_online = False
try:
    client.admin.command('ping')
    db_online = True
except Exception as e:
    pass

db = client.get_database('discord_bot')
servers_collection = db.get_collection('servers')
error_log_collection = db.get_collection('error_logs')

# Default log channel name
LOG_CHANNEL_NAME = 'observer'

# Embed colors
COLORS = {
    'yellow': 0xFAA61A, 'blue': 0x7289DA, 'purple': 0x9B59B6,
    'red': 0xF04747, 'green': 0x43B581, 'orange': 0xFFA500,  # Orange for editing
    'burnt_orange': 0xCC5500  # Burnt orange for deletion
}

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

def sanitize_content(content):
    return re.sub(r'[^a-zA-Z0-9\s.,!?@#$%^&*()_+=\[\]{};\'":<>?/🡫]', '', content).lower()

def format_datetime(dt):
    return dt.strftime('%B {S}, %Y @ %I:%M:%S%p').replace(' 0', ' ').replace('{S}', str(dt.day) + ('th' if 11 <= dt.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(dt.day % 10, 'th'))).lower()

async def ensure_log_channel(guild):
    guild_data = servers_collection.find_one({'_id': guild.id})
    log_channel = bot.get_channel(guild_data['log_channel_id']) if guild_data and 'log_channel_id' in guild_data else discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if not log_channel:
        log_channel = await guild.create_text_channel(LOG_CHANNEL_NAME, overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)})
        servers_collection.update_one({'_id': guild.id}, {'$set': {'log_channel_id': log_channel.id}}, upsert=True)
    return log_channel

async def send_log_message(guild_id, embed):
    guild_data = servers_collection.find_one({'_id': guild_id})
    if guild_data:
        channel = bot.get_channel(guild_data['log_channel_id'])
        if channel:
            await channel.send(embed=embed)

def create_embed(action, user, color, **fields):
    embed = discord.Embed(color=COLORS[color])
    embed.set_author(name=str(user), icon_url=user.avatar.url if user.avatar else None)
    embed.description = f"**{action}**\n" + "\n".join(
        f"<#{value}>" if key in ["channel", "from_channel", "to"] else sanitize_content(value) for key, value in fields.items()
    )
    embed.set_footer(text=f"user id: {user.id}")
    return embed

def log_error(error_message):
    error_log_collection.insert_one({'timestamp': datetime.utcnow(), 'error_message': error_message})

@bot.event
async def on_ready():
    print("Connected to Discord.")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servers"))
    for guild in bot.guilds:
        await ensure_log_channel(guild)
    if db_online:
        print("Database online.")
    else:
        print("Database offline.")
    print(f"Observing {len(bot.guilds)} servers.")

@bot.event
async def on_guild_join(guild):
    if not guild.me.guild_permissions.administrator:
        owner = guild.owner
        if owner:
            try:
                await owner.send("hello, i need **admin permissions** to function properly. please **re-invite** me with admin permissions.")
            except discord.Forbidden:
                pass
        await guild.leave()
    else:
        await ensure_log_channel(guild)

@bot.event
async def on_guild_remove(guild):
    servers_collection.delete_one({'_id': guild.id})

@bot.event
async def on_member_update(before, after):
    try:
        if before.display_name != after.display_name:
            await send_log_message(before.guild.id, create_embed("changed their nickname", after, 'yellow',
                before=f"{sanitize_content(before.display_name)}\n🡫", after=f"**{sanitize_content(after.display_name)}**"))
        if before.name != after.name:
            await send_log_message(before.guild.id, create_embed("changed their username", after, 'yellow',
                before=f"{sanitize_content(before.name)}\n🡫", after=f"**{sanitize_content(after.name)}**"))
    except Exception as e:
        log_error(f"error in on_member_update: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    try:
        current_time = datetime.utcnow()
        if before.channel is None and after.channel is not None:
            await send_log_message(member.guild.id, create_embed("joined a voice channel", member, 'blue', channel=after.channel.id, timestamp=format_datetime(current_time)))
        elif before.channel is not None and after.channel is None:
            await send_log_message(member.guild.id, create_embed("left a voice channel", member, 'purple', channel=before.channel.id, timestamp=format_datetime(current_time)))
        elif before.channel != after.channel:
            await send_log_message(member.guild.id, create_embed("moved voice channels", member, 'blue', from_channel=before.channel.id, to=after.channel.id, timestamp=format_datetime(current_time)))
    except Exception as e:
        log_error(f"error in on_voice_state_update: {e}")

@bot.event
async def on_member_join(member):
    try:
        await send_log_message(member.guild.id, create_embed("joined the server", member, 'green', timestamp=format_datetime(member.joined_at)))
    except Exception as e:
        log_error(f"error in on_member_join: {e}")

@bot.event
async def on_member_ban(guild, user):
    try:
        moderator = None
        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
            if entry.target.id == user.id:
                moderator = entry.user
                break
        await send_log_message(guild.id, create_embed("banned a user", user, 'red', moderator=f"{moderator} (id: {moderator.id})" if moderator else ''))
    except Exception as e:
        log_error(f"error in on_member_ban: {e}")

@bot.event
async def on_member_remove(member):
    try:
        moderator = None
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
            if entry.target.id == member.id:
                moderator = entry.user
                break
        await send_log_message(member.guild.id, create_embed("left or was kicked from the server", member, 'red', moderator=f"{moderator} (id: {moderator.id})" if moderator else "user left voluntarily or was kicked"))
    except Exception as e:
        log_error(f"error in on_member_remove: {e}")

@bot.event
async def on_message_edit(before, after):
    try:
        if before.content != after.content:
            # Ignore messages with images, files, or links
            if any(ext in before.content for ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', 'http://', 'https://')):
                return
            edit_time = datetime.utcnow()
            await send_log_message(before.guild.id, create_embed(
                "edited a message", before.author, 'orange',
                before=f"{sanitize_content(before.content)}\n🡫",
                after=f"**{sanitize_content(after.content)}**",
                channel=before.channel.id,
                timestamp=format_datetime(edit_time)
            ))
    except Exception as e:
        log_error(f"error in on_message_edit: {e}")

@bot.event
async def on_message_delete(message):
    try:
        # Fetch the audit log to find the moderator who deleted the message
        guild = message.guild
        async for entry in guild.audit_logs(action=discord.AuditLogAction.message_delete, limit=1):
            if entry.target.id == message.author.id:
                deleter = entry.user
                break
        else:
            deleter = None

        embed_fields = {
            'content': sanitize_content(message.content),
            'by': f"{message.author} (id: {message.author.id})",
            'channel': message.channel.id
        }
        if deleter:
            embed_fields['deleter'] = f"{deleter} (id: {deleter.id})"

        await send_log_message(message.guild.id, create_embed("deleted a message", deleter if deleter else message.author, 'burnt_orange', **embed_fields))
    except Exception as e:
        log_error(f"error in on_message_delete: {e}")

@bot.event
async def on_disconnect():
    pass

@bot.event
async def on_resumed():
    pass

if __name__ == '__main__':
    bot.run(TOKEN)
