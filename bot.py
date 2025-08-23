import os
import discord
from discord import app_commands
from discord.ext import commands
from supabase import create_client, Client
from flask import Flask
import threading
from datetime import datetime
from cryptography.fernet import Fernet
import traceback

# ==== 環境変数 ====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# ==== Supabase クライアント ====
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==== 暗号化用 Fernet ====
fernet = Fernet(ENCRYPTION_KEY.encode())

# ==== Discord Bot ====
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # スラッシュコマンド用

# ---- 認証コマンドの処理 ----
async def verify(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    user = interaction.user

    try:
        res = supabase.table("guild_settings").select("*").eq("guild_id", guild_id).execute()
        if not res.data:
            await interaction.response.send_message(
                "❌ このサーバーでは認証設定がまだ行われていません。",
                ephemeral=True
            )
            return

        setting = res.data[0]

        # 認証チャンネル制限
        channel_id = int(fernet.decrypt(setting["channel_id"].encode()).decode())
        if interaction.channel.id != channel_id:
            await interaction.response.send_message(
                "❌ このチャンネルでは認証できません。",
                ephemeral=True
            )
            return

        # ロール付与
        role_id = int(fernet.decrypt(setting["role_id"].encode()).decode())
        role = interaction.guild.get_role(role_id)

        if role is None:
            await interaction.response.send_message("❌ 設定されたロールが見つかりません。", ephemeral=True)
            return

        await user.add_roles(role)
        await interaction.response.send_message(
            f"✅ {user.mention} さんを認証しました！",
            ephemeral=True
        )

        # メッセージ削除（エラーは握りつぶす）
        try:
            await interaction.channel.purge(limit=1, check=lambda m: m.author == user)
        except Exception as e:
            print(f"メッセージ削除エラー: {e}")

    except Exception:
        traceback.print_exc()
        await interaction.response.send_message("❌ 認証中にエラーが発生しました。", ephemeral=True)


# ---- Bot 起動イベント ----
@bot.event
async def on_ready():
    try:
        tree.clear_commands(guild=None)  # 古い登録を削除

        tree.add_command(app_commands.Command(
            name="認証",
            description="サーバーで認証を受けます",
            callback=verify
        ))

        synced = await tree.sync()
        print(f"✅ {bot.user} としてログインしました")
        print(f"✅ {len(synced)} 件のコマンドを同期しました")
        for cmd in synced:
            print(f" - {cmd.name}")

    except Exception as e:
        print(f"❌ on_ready error: {e}")


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
