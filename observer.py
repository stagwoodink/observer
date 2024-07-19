import discord
from discord.ext import commands, tasks
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import re
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

# MongoDB setup
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client.get_database('discord_bot')
servers_collection = db.get_collection('servers')

# Log database setup
log_db = client.get_database('log')
error_log_collection = log_db.get_collection('error_logs')

# Default log channel name
LOG_CHANNEL_NAME = 'observer'

# Embed colors
COLOR_YELLOW = 0xFAA61A
COLOR_BLUE = 0x7289DA
COLOR_PURPLE = 0x9B59B6
COLOR_ORANGE = 0xF47B67
COLOR_RED = 0xF04747
COLOR_PINK = 0xE91E63
COLOR_GREEN = 0x43B581

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# In-memory cache for join times
join_cache = {}

def sanitize_content(content):
    sanitized = re.sub(r'[^a-zA-Z0-9\s\.\,\!\?\@\#\$\%\^\&\*\(\)\_\+\=\-\[\]\{\}\;\'\"\:\<\>\?\/]', '', content)
    return sanitized

async def ensure_log_channel(guild):
    guild_data = servers_collection.find_one({'_id': guild.id})
    log_channel = None

    if guild_data and 'log_channel_id' in guild_data:
        log_channel = bot.get_channel(guild_data['log_channel_id'])

    if not log_channel:
        log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
        if not log_channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False)
            }
            log_channel = await guild.create_text_channel(LOG_CHANNEL_NAME, overwrites=overwrites)
        servers_collection.update_one({'_id': guild.id}, {'$set': {'log_channel_id': log_channel.id}}, upsert=True)

    return log_channel

async def send_log_message(guild_id, embed=None):
    guild_data = servers_collection.find_one({'_id': guild_id})
    if guild_data:
        channel = bot.get_channel(guild_data['log_channel_id'])
        if channel and embed:
            await channel.send(embed=embed)

def create_embed(action, user, color, **fields):
    embed = discord.Embed(color=color)
    embed.set_author(name=str(user), icon_url=user.avatar.url if user.avatar else None)
    embed.title = action  # Added title to help identify action types in logs
    for name, value in fields.items():
        value = f"<#{value}>" if name in ["Channel", "From", "To"] else sanitize_content(value)
        embed.add_field(name=name, value=value, inline=False)
    embed.set_footer(text=f"User ID: {user.id}")
    return embed

def log_error(error_message):
    error_log_collection.insert_one({
        'timestamp': datetime.utcnow(),
        'error_message': error_message
    })

def format_duration(duration):
    seconds = duration.total_seconds()
    parts = []
    if seconds >= 3600:
        hours = int(seconds // 3600)
        parts.append(f"{hours}h")
        seconds %= 3600
    if seconds >= 60:
        minutes = int(seconds // 60)
        parts.append(f"{minutes}m")
        seconds %= 60
    if seconds > 0 or not parts:
        parts.append(f"{int(seconds)}s")
    return ''.join(parts)

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servers"))
    for guild in bot.guilds:
        await ensure_log_channel(guild)
    clear_cache.start()  # Start the cache clearing task

@bot.event
async def on_guild_join(guild):
    if not guild.me.guild_permissions.administrator:
        owner = guild.owner
        if owner:
            try:
                await owner.send("Hello, I need **admin permissions** to function properly. Please **re-invite** me with admin permissions.")
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
            await send_log_message(before.guild.id, create_embed("Nickname Change", after, COLOR_YELLOW, Before=before.display_name, After=f"**{after.display_name}**"))
        if before.name != after.name:
            await send_log_message(before.guild.id, create_embed("Name Change", after, COLOR_YELLOW, Before=before.name, After=f"**{after.name}**"))
        if before.avatar != after.avatar:
            await send_log_message(before.guild.id, create_embed("Avatar Change", after, COLOR_YELLOW))
    except Exception as e:
        log_error(f"Error in on_member_update: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    try:
        current_time = datetime.utcnow().replace(microsecond=0)

        if before.channel is None and after.channel is not None:
            action = "Joined Voice Channel"
            color = COLOR_BLUE
            fields = {'Channel': after.channel.id, 'Timestamp': current_time.isoformat()}
            await send_log_message(member.guild.id, create_embed(action, member, color, **fields))
            join_cache[(member.id, after.channel.id)] = current_time  # Cache join time

        elif before.channel is not None and after.channel is None:
            action = "Left Voice Channel"
            color = COLOR_PURPLE
            fields = {'Channel': before.channel.id, 'Timestamp': current_time.isoformat()}
            
            join_time = join_cache.pop((member.id, before.channel.id), None)  # Retrieve and remove from cache
            if join_time:
                duration = current_time - join_time
                fields['Duration'] = format_duration(duration)
            
            await send_log_message(member.guild.id, create_embed(action, member, color, **fields))
        
        elif before.channel != after.channel:
            action = "Moved Voice Channel"
            color = COLOR_BLUE
            fields = {'From': before.channel.id, 'To': after.channel.id, 'Timestamp': current_time.isoformat()}
            await send_log_message(member.guild.id, create_embed(action, member, color, **fields))
            
            join_time = join_cache.pop((member.id, before.channel.id), None)  # Retrieve and remove from cache
            if join_time:
                duration = current_time - join_time
                fields['Duration'] = format_duration(duration)
            
            join_cache[(member.id, after.channel.id)] = current_time  # Cache new join time
            
    except Exception as e:
        log_error(f"Error in on_voice_state_update: {e}")

@tasks.loop(minutes=10)
async def clear_cache():
    # Clear entries older than 1 hour from the cache
    cutoff = datetime.utcnow() - timedelta(hours=1)
    keys_to_remove = [key for key, timestamp in join_cache.items() if timestamp < cutoff]
    for key in keys_to_remove:
        del join_cache[key]

@bot.event
async def on_message_edit(before, after):
    try:
        if before.content != after.content:
            await send_log_message(before.guild.id, create_embed("Message Edited", before.author, COLOR_ORANGE, Before=sanitize_content(before.content), After=f"**{sanitize_content(after.content)}**"))
    except Exception as e:
        log_error(f"Error in on_message_edit: {e}")

@bot.event
async def on_message(message):
    try:
        if message.attachments or any(url in message.content for url in ['http://', 'https://']):
            await send_log_message(message.guild.id, create_embed("Message with Link/File", message.author, COLOR_PINK, Content=sanitize_content(message.content), Channel=message.channel.id))
        await bot.process_commands(message)
    except Exception as e:
        log_error(f"Error in on_message: {e}")

@bot.event
async def on_member_ban(guild, user):
    try:
        await send_log_message(guild.id, create_embed("User Banned", user, COLOR_RED))
    except Exception as e:
        log_error(f"Error in on_member_ban: {e}")

@bot.event
async def on_member_remove(member):
    try:
        await send_log_message(member.guild.id, create_embed("User Left/Kicked", member, COLOR_RED))
    except Exception as e:
        log_error(f"Error in on_member_remove: {e}")

@bot.event
async def on_member_join(member):
    try:
        await send_log_message(member.guild.id, create_embed("User Joined", member, COLOR_GREEN))
    except Exception as e:
        log_error(f"Error in on_member_join: {e}")

if __name__ == '__main__':
    bot.run(TOKEN)
