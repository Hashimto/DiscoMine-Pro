import os
import json
from cryptography.fernet import Fernet
import discord
from discord.ext import commands

# ====== 暗号化設定 ======
# 環境変数から暗号化キーを取得（Renderで設定）
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("環境変数 ENCRYPTION_KEY が設定されていません！")

fernet = Fernet(ENCRYPTION_KEY)

DATA_FILE = "config.json"

# 暗号化されたデータ読み込み
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "rb") as f:
        encrypted_data = f.read()
    if not encrypted_data:
        return {}
    try:
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode())
    except Exception:
        return {}

# データを暗号化して保存
def save_data(data):
    json_str = json.dumps(data)
    encrypted_data = fernet.encrypt(json_str.encode())
    with open(DATA_FILE, "wb") as f:
        f.write(encrypted_data)

# ====== Bot設定 ======
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# サーバーごとの設定データ
server_roles = load_data()

@bot.event
async def on_ready():
    print(f"✅ Botログイン完了: {bot.user}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setrole(ctx, role: discord.Role):
    server_roles[str(ctx.guild.id)] = role.id
    save_data(server_roles)
    await ctx.send(f"✅ このサーバーの認証ロールを `{role.name}` に設定しました。")

@bot.command()
async def showrole(ctx):
    role_id = server_roles.get(str(ctx.guild.id))
    if role_id:
        role = ctx.guild.get_role(role_id)
        await ctx.send(f"ℹ️ 現在設定されているロール: `{role.name}`")
    else:
        await ctx.send("⚠️ ロールがまだ設定されていません。")

bot.run(TOKEN)
