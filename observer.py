import discord
import os
import re
from discord.ext import commands
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

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
    embed.description = f"**{action}**\n"
    for name, value in fields.items():
        value = f"<#{value}>" if name in ["Channel", "From", "To"] else sanitize_content(value)
        embed.description += f"{name}: {value}\n"
    embed.set_footer(text=f"User ID: {user.id}")
    return embed

def log_error(error_message):
    error_log_collection.insert_one({
        'timestamp': datetime.utcnow(),
        'error_message': error_message
    })

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servers"))
    for guild in bot.guilds:
        await ensure_log_channel(guild)

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
        if before.channel != after.channel:
            action, color, fields = (
                ("Joined Voice Channel", COLOR_BLUE, {'Channel': after.channel.id})
                if before.channel is None else
                ("Left Voice Channel", COLOR_PURPLE, {'Channel': before.channel.id})
                if after.channel is None else
                ("Moved Voice Channel", COLOR_BLUE, {'From': before.channel.id, 'To': after.channel.id})
            )
            await send_log_message(member.guild.id, create_embed(action, member, color, **fields))
    except Exception as e:
        log_error(f"Error in on_voice_state_update: {e}")

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
