import os
import discord
from discord import app_commands
from discord.ext import commands
import requests
import json
from cryptography.fernet import Fernet
import psycopg2

# ========== 環境変数 ==========
TOKEN = os.getenv("DISCORD_TOKEN")
FERNET_KEY = os.getenv("FERNET_KEY")  # 暗号化キー
DATABASE_URL = os.getenv("DATABASE_URL")  # Supabase PostgreSQL URL
XUID_API_URL = "https://api.geysermc.org/v2/xbox/xuid/{gamertag}"
GAMERTAG_API_URL = "https://api.geysermc.org/v2/xbox/gamertag/{xuid}"

# ========== 暗号化ユーティリティ ==========
fernet = Fernet(FERNET_KEY)

def encrypt_data(data: dict) -> str:
    return fernet.encrypt(json.dumps(data).encode()).decode()

def decrypt_data(data: str) -> dict:
    try:
        return json.loads(fernet.decrypt(data.encode()).decode())
    except Exception:
        return {}

# ========== データ永続化 ==========
LOCAL_FILE = "server_roles.json"
server_roles = {}  # { guild_id: {"role_id": 123, "channel_id": 456} }

def load_data():
    global server_roles
    if os.path.exists(LOCAL_FILE):
        with open(LOCAL_FILE, "r") as f:
            encrypted = f.read().strip()
            if encrypted:
                server_roles = decrypt_data(encrypted)
    else:
        server_roles = {}

def save_data():
    with open(LOCAL_FILE, "w") as f:
        f.write(encrypt_data(server_roles))

    # PostgreSQLにもバックアップ
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS server_roles (
                guild_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
        """)
        for gid, data in server_roles.items():
            cur.execute("""
                INSERT INTO server_roles (guild_id, data)
                VALUES (%s, %s)
                ON CONFLICT (guild_id)
                DO UPDATE SET data = EXCLUDED.data;
            """, (gid, json.dumps(data)))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("⚠️ Supabase保存エラー:", e)

# 初期ロード
load_data()

# ========== Bot設定 ==========
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Botがログインしました: {bot.user}")

# ========== コマンド ==========

# ロール設定コマンド（管理者専用）
@tree.command(name="ロール設定", description="認証に付与するロールを設定します（管理者専用）")
@app_commands.checks.has_permissions(administrator=True)
async def setrole(interaction: discord.Interaction, role: discord.Role):
    guild_id = str(interaction.guild.id)
    server_roles[guild_id] = {
        "role_id": role.id,
        "channel_id": interaction.channel.id
    }
    save_data()
    await interaction.response.send_message(
        f"✅ このサーバーの認証ロールを `{role.name}` に設定しました。\n"
        f"認証専用チャンネル: {interaction.channel.mention}"
    )

# 認証コマンド
@tree.command(name="認証", description="Minecraftのゲーマータグを使って認証します")
async def verify(interaction: discord.Interaction, ゲーマータグ: str):
    guild_id = str(interaction.guild.id)
    settings = server_roles.get(guild_id)

    # チャンネルチェック
    if not settings or interaction.channel.id != settings["channel_id"]:
        await interaction.response.send_message("⚠️ このチャンネルでは認証できません。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # XUID取得
    try:
        xuid_response = requests.get(XUID_API_URL.format(gamertag=ゲーマータグ))
        xuid_response.raise_for_status()
        xuid = xuid_response.json().get("xuid")
    except Exception:
        await interaction.followup.send("⚠️ XUID取得に失敗しました。")
        return

    if not xuid:
        await interaction.followup.send("⚠️ XUIDが見つかりません。")
        return

    # Gamertag確認
    try:
        gamertag_response = requests.get(GAMERTAG_API_URL.format(xuid=xuid))
        gamertag_response.raise_for_status()
        returned_gamertag = gamertag_response.json().get("gamertag")
    except Exception:
        await interaction.followup.send("⚠️ ユーザー確認に失敗しました。")
        return

    if ゲーマータグ.lower() == returned_gamertag.lower():
        guild = interaction.guild
        role = guild.get_role(settings["role_id"])
        member = interaction.user
        if role and member:
            await member.add_roles(role)
            await interaction.followup.send(f"✅ {ゲーマータグ} さんを認証しました！")
        else:
            await interaction.followup.send("⚠️ ロールまたはメンバーが見つかりません。")
    else:
        await interaction.followup.send("❌ 認証に失敗しました。IDが一致しません。")

# エラーハンドリング
@setrole.error
async def setrole_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("⚠️ このコマンドを実行できるのは管理者のみです。", ephemeral=True)

# =============================
bot.run(TOKEN)
