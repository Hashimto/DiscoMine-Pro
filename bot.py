import os
import json
import threading
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from flask import Flask

from supabase import create_client, Client
from cryptography.fernet import Fernet

# ==============================
# Flask (Render の Web Service 用ダミーサーバー)
# ==============================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ==============================
# Supabase 接続
# ==============================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==============================
# 暗号化キー（環境変数から取得）
# ==============================
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY が設定されていません！")

fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()

# ==============================
# Discord Bot 設定
# ==============================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)

# ==============================
# DB 保存/取得関数
# ==============================
def save_guild_config(guild_id: int, channel_id: int, role_id: int):
    encrypted_channel = encrypt(str(channel_id))
    encrypted_role = encrypt(str(role_id))
    created_at = datetime.utcnow().isoformat()

    supabase.table("guild_configs").upsert({
        "guild_id": str(guild_id),
        "channel_id": encrypted_channel,
        "role_id": encrypted_role,
        "created_at": created_at
    }).execute()

def get_guild_config(guild_id: int):
    res = supabase.table("guild_configs").select("*").eq("guild_id", str(guild_id)).execute()
    if res.data:
        data = res.data[0]
        return {
            "channel_id": int(decrypt(data["channel_id"])),
            "role_id": int(decrypt(data["role_id"]))
        }
    return None

# ==============================
# スラッシュコマンド
# ==============================
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} コマンドを同期しました")
    except Exception as e:
        print(f"❌ コマンド同期失敗: {e}")

    print(f"✅ ログイン成功: {bot.user}")

# 設定コマンド（管理者のみ）
@bot.tree.command(name="設定", description="認証用チャンネルとロールを設定します（管理者専用）")
@app_commands.describe(
    channel="認証専用チャンネル",
    role="認証成功時に付与するロール"
)
@app_commands.checks.has_permissions(administrator=True)
async def 設定(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    save_guild_config(interaction.guild.id, channel.id, role.id)
    await interaction.response.send_message(f"✅ 認証チャンネルを {channel.mention}、ロールを {role.name} に設定しました！", ephemeral=True)

# 認証コマンド（ユーザーが実行）
@bot.tree.command(name="認証", description="サーバーの認証を行います")
async def 認証(interaction: discord.Interaction):
    config = get_guild_config(interaction.guild.id)
    if not config:
        await interaction.response.send_message("❌ サーバー管理者がまだ設定していません。", ephemeral=True)
        return

    # 認証専用チャンネル以外では実行禁止
    if interaction.channel.id != config["channel_id"]:
        await interaction.response.send_message("❌ 認証専用チャンネルで実行してください。", ephemeral=True)
        return

    # ロール付与
    role = interaction.guild.get_role(config["role_id"])
    if role:
        await interaction.user.add_roles(role)
        await interaction.response.send_message(f"✅ {interaction.user.mention} に {role.name} を付与しました！", ephemeral=True)

        # 認証メッセージは削除（チャンネルをきれいに保つ）
        try:
            await interaction.channel.purge(limit=1, check=lambda m: m.id == interaction.id)
        except Exception:
            pass
    else:
        await interaction.response.send_message("❌ 設定されたロールが見つかりません。", ephemeral=True)

# ==============================
# 起動
# ==============================
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(os.getenv("DISCORD_TOKEN"))
