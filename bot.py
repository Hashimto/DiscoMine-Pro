import os
import discord
from discord.ext import commands
import asyncpg
import json
from cryptography.fernet import Fernet

# ===== 環境変数 =====
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("FERNET_KEY").encode()  # Renderで作成したFernetキー

fernet = Fernet(SECRET_KEY)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== PostgreSQL接続 =====
async def pg_connect():
    return await asyncpg.connect(DATABASE_URL)

# ===== ギルドごとのロール保存 =====
async def pg_set_role(guild_id: int, role_id: int):
    conn = await pg_connect()
    await conn.execute(
        "INSERT INTO guild_roles (guild_id, role_id) VALUES ($1, $2) "
        "ON CONFLICT (guild_id) DO UPDATE SET role_id = $2",
        guild_id, role_id
    )
    await conn.close()

async def pg_get_role(guild_id: int):
    conn = await pg_connect()
    row = await conn.fetchrow("SELECT role_id FROM guild_roles WHERE guild_id = $1", guild_id)
    await conn.close()
    return row["role_id"] if row else None

# ===== Botイベント =====
@bot.event
async def on_ready():
    print(f"✅ Botがログインしました: {bot.user}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setrole(ctx, role: discord.Role):
    await pg_set_role(ctx.guild.id, role.id)
    await ctx.send(f"✅ このサーバーの認証用ロールを **{role.name}** に設定しました。")

# ===== verifyコマンド例（JSON暗号化も可能） =====
@bot.command()
async def verify(ctx, gamertag: str):
    role_id = await pg_get_role(ctx.guild.id)
    if not role_id:
        await ctx.send("⚠️ ロールが設定されていません。管理者に `!setrole` をお願いしてください。")
        return

    role = ctx.guild.get_role(role_id)
    member = ctx.author
    if role and member:
        await member.add_roles(role)
        await ctx.send(f"✅ {member.name} にロール **{role.name}** を付与しました。")
    else:
        await ctx.send("⚠️ ロールまたはメンバーが見つかりません。")

bot.run(TOKEN)
