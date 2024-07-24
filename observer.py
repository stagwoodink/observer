import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import re
import yaml
from datetime import datetime
from functools import wraps
import asyncio
import aiohttp

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Default log channel name
LOG_CHANNEL_NAME = 'observer'

# Embed colors
COLORS = {
    'yellow': 0xFAA61A, # Yellow for user-info change reports
    'blue': 0x7289DA,  # Blue for joining a voice channel reports
    'purple': 0x9B59B6,  # Purple for leaving the voice channel reports
    'red': 0xF04747,  # Red for leaving the server reports
    'green': 0x43B581,  # Green for joining the server reports
    'orange': 0xFFA500,  # Orange for editing reports
    'burnt_orange': 0xCC5500,  # Burnt orange for message deletion reports
    'rich_pink': 0xFF1493,  # Rich pink for attachment reports
    'white': 0xFFFFFF,  # White for link reports
    'black': 0x000000  # Black for code block reports
}

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def sanitize_content(content):
    return re.sub(r'[^a-zA-Z0-9\s.,!?@#$%^&*()_+=\\[\\]{};\'":<>?/🡫]', '', content).lower()

def escape_codeblock(content):
    return content.replace("`", "\`")

def format_datetime(dt):
    return dt.strftime('%B {S}, %Y @ %I:%M:%S%p').replace(' 0', ' ').replace('{S}', str(dt.day) + ('th' if 11 <= dt.day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(dt.day % 10, 'th'))).lower()

def load_yaml():
    try:
        with open('data.yaml', 'r') as file:
            return yaml.safe_load(file) or {}
    except FileNotFoundError:
        return {}

def save_yaml(data):
    with open('data.yaml', 'w') as file:
        yaml.safe_dump(data, file)

def get_guild_data(guild_id):
    data = load_yaml()
    return data.get(str(guild_id), {})

def update_guild_data(guild_id, key, value):
    data = load_yaml()
    if str(guild_id) not in data:
        data[str(guild_id)] = {}
    data[str(guild_id)][key] = value
    save_yaml(data)

async def ensure_log_channel(guild):
    guild_data = get_guild_data(guild.id)
    log_channel_id = guild_data.get('log_channel_id')
    log_channel = bot.get_channel(log_channel_id) if log_channel_id else None
    
    # Check if the log channel exists in the guild
    if not log_channel or log_channel not in guild.text_channels:
        log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
        if not log_channel:
            log_channel = await guild.create_text_channel(LOG_CHANNEL_NAME, overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)})
        update_guild_data(guild.id, 'log_channel_id', log_channel.id)
    
    return log_channel

async def send_log_message(guild_id, embed):
    guild_data = get_guild_data(guild_id)
    channel = bot.get_channel(guild_data.get('log_channel_id'))
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"Error sending log message: {e}")

def create_embed(action, user, color, **fields):
    embed = discord.Embed(color=COLORS[color])
    embed.set_author(name=str(user), icon_url=user.avatar.url if user.avatar else None)
    embed.description = f"**[{action}]({fields.get('url')})**\n" + "\n".join(
        f"<#{value}>" if key in ["channel", "from_channel", "to"] else sanitize_content(value) for key, value in fields.items() if key != 'url'
    )
    embed.set_footer(text=f"user id: {user.id}")
    return embed

def ignore_bots(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if len(args) > 0:
            if isinstance(args[0], discord.Member) or isinstance(args[0], discord.User):
                if args[0].bot:
                    return
            elif isinstance(args[0], discord.Message) and args[0].author.bot:
                return
        return await func(*args, **kwargs)
    return wrapper

@bot.event
async def on_ready():
    print("Connected to Discord.")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{len(bot.guilds)} servers"))
    for guild in bot.guilds:
        await ensure_log_channel(guild)
    print(f"Observing {len(bot.guilds)} servers.")

@bot.event
@ignore_bots
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
    data = load_yaml()
    if str(guild.id) in data:
        del data[str(guild.id)]
        save_yaml(data)

@bot.event
@ignore_bots
async def on_member_update(before, after):
    try:
        if before.display_name != after.display_name:
            await send_log_message(before.guild.id, create_embed("changed their nickname", after, 'yellow',
                before=f"{sanitize_content(before.display_name)}\n🡫", after=f"**{sanitize_content(after.display_name)}**"))
        if before.name != after.name:
            await send_log_message(before.guild.id, create_embed("changed their username", after, 'yellow',
                before=f"{sanitize_content(before.name)}\n🡫", after=f"**{sanitize_content(after.name)}**"))
    except Exception as e:
        print(f"Error in on_member_update: {e}")

@bot.event
@ignore_bots
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
        print(f"Error in on_voice_state_update: {e}")

@bot.event
@ignore_bots
async def on_member_join(member):
    try:
        await send_log_message(member.guild.id, create_embed("joined the server", member, 'green', timestamp=format_datetime(member.joined_at)))
    except Exception as e:
        print(f"Error in on_member_join: {e}")

@bot.event
@ignore_bots
async def on_member_ban(guild, user):
    try:
        moderator = None
        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
            if entry.target.id == user.id:
                moderator = entry.user
                break
        await send_log_message(guild.id, create_embed("banned a user", user, 'red', moderator=f"{moderator} (id: {moderator.id})" if moderator else ''))
    except Exception as e:
        print(f"Error in on_member_ban: {e}")

@bot.event
@ignore_bots
async def on_member_remove(member):
    try:
        moderator = None
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
            if entry.target.id == member.id:
                moderator = entry.user
                break
        await send_log_message(member.guild.id, create_embed("left or was kicked from the server", member, 'red', moderator=f"{moderator} (id: {moderator.id})" if moderator else "user left voluntarily or was kicked"))
    except Exception as e:
        print(f"Error in on_member_remove: {e}")

@bot.event
@ignore_bots
async def on_message_edit(before, after):
    try:
        if before.content != after.content:
            # Ignore messages with images, files, or links
            if any(ext in before.content for ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', 'http://', 'https://')):
                return
            edit_time = datetime.utcnow()
            await send_log_message(before.guild.id, create_embed(
                "edited a message", before.author, 'orange',
                before=f"{sanitize_content(before.content)}\n🡫", after=f"**{sanitize_content(after.content)}**",
                channel=before.channel.id, url=before.jump_url, timestamp=format_datetime(edit_time)
            ))
    except Exception as e:
        print(f"Error in on_message_edit: {e}")

@bot.event
@ignore_bots
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
        print(f"Error in on_message_delete: {e}")

@bot.event
@ignore_bots
async def on_message(message):
    try:
        if message.attachments:
            attachment_urls = "\n\n".join(attachment.url for attachment in message.attachments)
            action = "sent an attachment" if len(message.attachments) == 1 else "sent attachments"
            await send_log_message(message.guild.id, create_embed(
                action, message.author, 'rich_pink',
                attachments=attachment_urls,
                channel=message.channel.id, url=message.jump_url
            ))

        # Check for links in the message content
        link_pattern = re.compile(r'https?://\S+')
        links = link_pattern.findall(message.content)
        if links:
            link_urls = "\n\n".join(links)
            action = "sent a link" if len(links) == 1 else "sent links"
            await send_log_message(message.guild.id, create_embed(
                action, message.author, 'white',
                links=link_urls,
                channel=message.channel.id, url=message.jump_url
            ))

        # Check for code blocks in the message content
        codeblock_pattern = re.compile(r'```(.*?)```', re.DOTALL)
        codeblocks = codeblock_pattern.findall(message.content)
        if codeblocks:
            escaped_codeblocks = "\n\n".join(f"```{escape_codeblock(codeblock)}```" for codeblock in codeblocks)
            await send_log_message(message.guild.id, create_embed(
                "sent code", message.author, 'black',
                content=escaped_codeblocks,
                channel=message.channel.id, url=message.jump_url
            ))

        # Check for inline code blocks in the message content
        inline_codeblock_pattern = re.compile(r'`([^`]*)`')
        inline_codeblocks = inline_codeblock_pattern.findall(message.content)
        if inline_codeblocks:
            escaped_inline_codeblocks = "\n\n".join(f"`{escape_codeblock(inline_codeblock)}`" for inline_codeblock in inline_codeblocks)
            await send_log_message(message.guild.id, create_embed(
                "sent code", message.author, 'black',
                content=escaped_inline_codeblocks,
                channel=message.channel.id, url=message.jump_url
            ))
    except Exception as e:
        print(f"Error in on_message: {e}")

@bot.event
async def on_disconnect():
    pass

@bot.event
async def on_resumed():
    pass

if __name__ == '__main__':
    bot.run(TOKEN)
