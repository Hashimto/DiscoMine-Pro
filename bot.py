import os
import discord
from discord.ext import commands
from supabase import create_client, Client
from flask import Flask
import threading
from datetime import datetime
from cryptography.fernet import Fernet

# ==== 環境変数 ====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")  # 追加

# ==== Supabase クライアント ====
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==== 暗号化用 Fernet ====
fernet = Fernet(ENCRYPTION_KEY.encode())

# ==== Discord Bot ====
intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---- Bot 起動イベント ----
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

# ---- 認証設定コマンド ----
@bot.command(name="set_verify")
@commands.has_permissions(administrator=True)
async def set_verify(ctx, channel_id: int, role_id: int):
    guild_id = ctx.guild.id

    # データを暗号化して保存
    data = {
        "guild_id": str(guild_id),
        "channel_id": fernet.encrypt(str(channel_id).encode()).decode(),
        "role_id": fernet.encrypt(str(role_id).encode()).decode(),
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        supabase.table("guild_settings").upsert(data).execute()
        await ctx.send(f"✅ 認証設定を保存しました。\nChannel: <#{channel_id}> | Role: <@&{role_id}>")
    except Exception as e:
        await ctx.send("❌ データ保存中にエラーが発生しました。")
        print(f"Supabase Error: {e}")

# ---- 認証コマンド ----
@bot.command(name="verify")
async def verify(ctx):
    guild_id = str(ctx.guild.id)
    user = ctx.author

    try:
        res = supabase.table("guild_settings").select("*").eq("guild_id", guild_id).execute()
        if not res.data:
            await ctx.send("❌ このサーバーでは認証設定がまだ行われていません。")
            return

        setting = res.data[0]

        # 復号化
        role_id = int(fernet.decrypt(setting["role_id"].encode()).decode())
        role = ctx.guild.get_role(role_id)

        if role is None:
            await ctx.send("❌ 設定されたロールが見つかりません。")
            return

        await user.add_roles(role)
        await ctx.send(f"✅ {user.mention} さんを認証しました！")
    except Exception as e:
        await ctx.send("❌ 認証中にエラーが発生しました。")
        print(f"Verify Error: {e}")

# ---- Flask (keep-alive 用) ----
app = Flask(__name__)

@app.route("/")
def index():
    return "Bot is running!"

def run_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ==== メイン処理 ====
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(DISCORD_TOKEN)
