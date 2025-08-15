import os
import json
import discord
from discord.ext import commands
import requests
from flask import Flask
import threading
from cryptography.fernet import Fernet

# ====== Flaskのダミーサーバー（Renderでタイムアウト防止） ======
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run)
    t.start()

# ====== 暗号化設定 ======
FERNET_KEY = os.getenv("FERNET_KEY")  # 事前に生成してRenderの環境変数に設定
fernet = Fernet(FERNET_KEY)

CONFIG_FILE = "data/config.json"

# 初回起動時にファイルがなければ作成
if not os.path.exists(CONFIG_FILE):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        encrypted_empty_data = fernet.encrypt(json.dumps({}).encode())
        f.write(encrypted_empty_data)

def load_config():
    with open(CONFIG_FILE, "rb") as f:
        encrypted_data = f.read()
    decrypted_data = fernet.decrypt(encrypted_data).decode()
    return json.loads(decrypted_data)

def save_config(data):
    with open(CONFIG_FILE, "wb") as f:
        encrypted_data = fernet.encrypt(json.dumps(data).encode())
        f.write(encrypted_data)

# ====== Discord Bot設定 ======
TOKEN = os.getenv("DISCORD_TOKEN")
XUID_API_URL = "https://api.geysermc.org/v2/xbox/xuid/{gamertag}"
GAMERTAG_API_URL = "https://api.geysermc.org/v2/xbox/gamertag/{xuid}"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Botがログインしました: {bot.user}")

# 管理者がロールを設定するコマンド
@bot.command()
@commands.has_permissions(administrator=True)
async def setrole(ctx, role: discord.Role):
    config = load_config()
    config[str(ctx.guild.id)] = role.id
    save_config(config)
    await ctx.send(f"✅ このサーバーの認証ロールを `{role.name}` に設定しました。")

# 認証コマンド
@bot.command()
async def verify(ctx, gamertag: str):
    config = load_config()
    role_id = config.get(str(ctx.guild.id))
    if not role_id:
        await ctx.send("⚠️ このサーバーでは認証ロールが設定されていません。管理者が `!setrole @ロール` で設定してください。")
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
        role = ctx.guild.get_role(role_id)
        member = ctx.guild.get_member(ctx.author.id)
        if role and member:
            await member.add_roles(role)
            await ctx.send(f"✅ {gamertag} さんを認証しました！")
        else:
            await ctx.send("⚠️ ロールまたはメンバーが見つかりません。")
    else:
        await ctx.send("❌ 認証に失敗しました。IDが一致しません。")

# ====== 起動 ======
keep_alive()
bot.run(TOKEN)
