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

# ---- 認証コマンドの処理 (/認証) ----
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


# ---- 認証設定コマンド (/認証設定) ----
async def auth_setting(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    guild_id = str(interaction.guild.id)

    # 管理者チェック
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 管理者専用のコマンドです。", ephemeral=True)
        return

    try:
        encrypted_channel_id = fernet.encrypt(str(channel.id).encode()).decode()
        encrypted_role_id = fernet.encrypt(str(role.id).encode()).decode()

        res = supabase.table("guild_settings").select("*").eq("guild_id", guild_id).execute()

        if res.data:
            # すでに設定あり → 更新
            supabase.table("guild_settings").update({
                "channel_id": encrypted_channel_id,
                "role_id": encrypted_role_id,
            }).eq("guild_id", guild_id).execute()
            action = "更新"
        else:
            # 初回 → 保存
            supabase.table("guild_settings").insert({
                "guild_id": guild_id,
                "channel_id": encrypted_channel_id,
                "role_id": encrypted_role_id,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            action = "保存"

        await interaction.response.send_message(
            f"✅ 認証設定を{action}しました。\n"
            f"- チャンネル: {channel.mention}\n"
            f"- ロール: {role.mention}",
            ephemeral=True
        )

    except Exception:
        traceback.print_exc()
        await interaction.response.send_message("❌ 設定中にエラーが発生しました。", ephemeral=True)


# ---- 認証設定確認コマンド (/認証設定確認) ----
async def check_auth_setting(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)

    # 管理者チェック
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 管理者専用のコマンドです。", ephemeral=True)
        return

    try:
        res = supabase.table("guild_settings").select("*").eq("guild_id", guild_id).execute()

        if not res.data:
            await interaction.response.send_message("❌ このサーバーには認証設定が保存されていません。", ephemeral=True)
            return

        setting = res.data[0]
        channel_id = int(fernet.decrypt(setting["channel_id"].encode()).decode())
        role_id = int(fernet.decrypt(setting["role_id"].encode()).decode())

        channel = interaction.guild.get_channel(channel_id)
        role = interaction.guild.get_role(role_id)

        await interaction.response.send_message(
            f"📌 現在の認証設定:\n"
            f"- チャンネル: {channel.mention if channel else '❌ 不明'}\n"
            f"- ロール: {role.mention if role else '❌ 不明'}",
            ephemeral=True
        )

    except Exception:
        traceback.print_exc()
        await interaction.response.send_message("❌ 設定確認中にエラーが発生しました。", ephemeral=True)


# ---- Bot 起動イベント ----
@bot.event
async def on_ready():
    try:
        tree.clear_commands(guild=None)

        # /認証
        tree.add_command(app_commands.Command(
            name="認証",
            description="サーバーで認証を受けます",
            callback=verify
        ))

        # /認証設定
        tree.add_command(app_commands.Command(
            name="認証設定",
            description="認証に使うチャンネルとロールを設定します（管理者専用）",
            callback=auth_setting,
            options=[
                app_commands.Argument(
                    name="channel",
                    description="認証用のチャンネル",
                    type=discord.AppCommandOptionType.channel
                ),
                app_commands.Argument(
                    name="role",
                    description="認証時に付与するロール",
                    type=discord.AppCommandOptionType.role
                )
            ]
        ))

        # /認証設定確認
        tree.add_command(app_commands.Command(
            name="認証設定確認",
            description="現在の認証設定を確認します（管理者専用）",
            callback=check_auth_setting
        ))

        synced = await tree.sync()
        print(f"✅ {bot.user} としてログインしました")
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
