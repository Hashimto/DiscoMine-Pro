import os
import json
import discord
import requests
from discord.ext import commands
from cryptography.fernet import Fernet
import threading
from flask import Flask

# ===== Flaskダミーサーバー（Renderでタイムアウト防止） =====
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# ===== 暗号化設定 =====
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
fernet = Fernet(ENCRYPTION_KEY.encode())

DATA_FILE = "server_roles.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "rb") as f:
        encrypted_data = f.read()
        if not encrypted_data:
            return {}
        decrypted_data = fernet.decrypt(encrypted_data).decode()
        return json.loads(decrypted_data)

def save_data(data):
    encrypted_data = fernet.encrypt(json.dumps(data).encode())
    with open(DATA_FILE, "wb") as f:
        f.write(encrypted_data)

server_roles = load_data()

# ===== Discord Bot設定 =====
TOKEN = os.getenv("DISCORD_TOKEN")
XUID_API_URL = "https://api.geysermc.org/v2/xbox/xuid/{gamertag}"
GAMERTAG_API_URL = "https://api.geysermc.org/v2/xbox/gamertag/{xuid}"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Botがログインしました: {bot.user}")

# ===== サーバーごとのロール設定コマンド（管理者用） =====
@bot.command()
@commands.has_permissions(administrator=True)
async def setrole(ctx, role: discord.Role):
    server_roles[str(ctx.guild.id)] = role.id
    save_data(server_roles)
    await ctx.send(f"✅ このサーバーの認証ロールを `{role.name}` に設定しました。")

@bot.command()
@commands.has_permissions(administrator=True)
async def clearrole(ctx):
    if str(ctx.guild.id) in server_roles:
        del server_roles[str(ctx.guild.id)]
        save_data(server_roles)
        await ctx.send("🗑️ 認証ロール設定を削除しました。")
    else:
        await ctx.send("⚠️ このサーバーには認証ロール設定がありません。")

# ===== DMでの認証コマンド =====
@bot.command()
async def verify(ctx, gamertag: str):
    if ctx.guild is not None:
        await ctx.send("⚠️ このコマンドはDMで実行してください。")
        return

    try:
        xuid_response = requests.get(XUID_API_URL.format(gamertag=gamertag))
        xuid_response.raise_for_status()
        xuid = xuid_response.json().get("xuid")
    except Exception:
        await ctx.send("⚠️ XUID取得に失敗しました。")
        return

    if not xuid:
        await ctx.send("⚠️ XUIDが見つかりません。")
        return

    try:
        gamertag_response = requests.get(GAMERTAG_API_URL.format(xuid=xuid))
        gamertag_response.raise_for_status()
        returned_gamertag = gamertag_response.json().get("gamertag")
    except Exception:
        await ctx.send("⚠️ ユーザー確認に失敗しました。")
        return

    if gamertag.lower() == returned_gamertag.lower():
        success_count = 0
        for guild in bot.guilds:
            role_id = server_roles.get(str(guild.id))
            if role_id:
                member = guild.get_member(ctx.author.id)
                role = guild.get_role(role_id)
                if member and role:
                    await member.add_roles(role)
                    success_count += 1

        await ctx.send(f"✅ 認証成功！ {success_count} サーバーでロールを付与しました。")
    else:
        await ctx.send("❌ 認証に失敗しました。IDが一致しません。")

keep_alive()
bot.run(TOKEN)
