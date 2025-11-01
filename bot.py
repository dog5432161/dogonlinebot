import os
import discord
from discord.ext import commands
from discord import app_commands, ui, Interaction, ButtonStyle
from dotenv import load_dotenv
from sys import exit
import asyncio
import threading

# --- 웹 서버(API) 기능을 위한 import ---
from flask import Flask, request, jsonify

# --- 환경 설정 및 변수 로드 ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
REPORT_CHANNEL_ID = int(os.getenv('REPORT_CHANNEL_ID', 0))
API_SECRET_KEY = os.getenv('API_SECRET_KEY')

if TOKEN is None:
    print("===================================================================")
    print("❌ 오류: DISCORD_TOKEN 환경 변수를 로드하지 못했습니다.")
    exit()
else:
    print(f"✅ 토큰 로드 성공! (시작: {TOKEN[:5]}... 끝: {TOKEN[-5:]})")

if not REPORT_CHANNEL_ID or not API_SECRET_KEY:
    print("⚠️ 경고: REPORT_CHANNEL_ID 또는 API_SECRET_KEY가 설정되지 않았습니다. 신고 기능이 작동하지 않을 수 있습니다.")
# -----------------------------


# --- [추가] 음성 채널 역할 부여 기능에 필요한 ID ---
# 1. 유저가 접속할 음성 채널의 ID입니다. (제공해주신 ID)
TARGET_VOICE_CHANNEL_ID = 1432698753923420180

# 2. [!!! 필수 수정 !!!]
#    음성 채널 접속 시 부여할 역할의 ID입니다.
#    (예: '음성채팅중' 역할 우클릭 > 'ID 복사하기')
TARGET_ROLE_ID = 1433386189095698442  # 👈 이 숫자를 꼭 실제 역할 ID로 수정하세요!
# ----------------------------------------------------


# --- 봇 설정 (인텐트 수정됨) ---
intents = discord.Intents.default()
intents.message_content = True  # !명령어, on_message를 위해 필요
intents.members = True          # 역할 부여, DM 발송, 닉네임 변경을 위해 필요
intents.voice_states = True     # [수정] 음성 채널 감지를 위해 이 라인이 추가되었습니다.

bot = commands.Bot(command_prefix='!', intents=intents)

# 봇에게 부여할 '인증' 역할의 이름
AUTH_ROLE_NAME = '인증'


#############################################################################
## 🚨 마인크래프트 신고 API 부분 (변경사항 없음)
#############################################################################

flask_app = Flask(__name__)

@flask_app.route('/report', methods=['POST'])
def handle_report():
    auth_key = request.headers.get('Authorization')
    if auth_key != API_SECRET_KEY:
        print(f"❌ 신고 API: 인증 실패 (잘못된 키: {auth_key})")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.json
    reporter = data.get('reporter')
    suspect = data.get('suspect')
    reason = data.get('reason')

    if not all([reporter, suspect, reason]):
        print(f"❌ 신고 API: 데이터 누락 ({data})")
        return jsonify({"status": "error", "message": "Missing data"}), 400

    print(f"✅ 신고 API: {reporter}님이 {suspect}님을 신고 (사유: {reason})")
    bot.loop.call_soon_threadsafe(
        asyncio.create_task,
        send_report_to_channel(reporter, suspect, reason)
    )
    return jsonify({"status": "success", "message": "Report received"}), 200

async def send_report_to_channel(reporter, suspect, reason):
    """신고 내용을 실제 디스코드 채널에 텍스트 메시지로 보내는 함수"""
    channel = bot.get_channel(REPORT_CHANNEL_ID)
    if not channel:
        print(f"❌ 디스코드 오류: 채널 ID({REPORT_CHANNEL_ID})를 찾을 수 없습니다.")
        return

    message_content = (
        f"**`{reporter}`**님이 **`{suspect}`**에게 살해당하여 신고했습니다!\n"
        f"> **신고 내용:** {reason}"
    )
    await channel.send(message_content)


#############################################################################
## 🔑 디스코드 유저 인증 시스템 부분 (변경사항 없음)
#############################################################################

# --- 모달(Modal) 클래스 정의: 팝업 창 ---
class VerificationModal(ui.Modal, title='📝 유저 인증 정보 입력'):
    mc_nickname = ui.TextInput(
        label='마인크래프트 닉네임 (가입 시 닉네임)',
        placeholder='예: DogUser123',
        required=True,
        max_length=32
    )

    purpose = ui.TextInput(
        label='서버 참여 목적',
        placeholder='예: 친구들과 함께 경제 활동',
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        guild = interaction.guild
        entered_nickname = str(self.mc_nickname)
        final_nickname = f"[ 시민 ] {entered_nickname}"

        # 1. 역할 부여
        auth_role = discord.utils.get(guild.roles, name=AUTH_ROLE_NAME)
        if auth_role:
            try:
                await user.add_roles(auth_role)
            except discord.Forbidden:
                await interaction.followup.send(
                    '❌ 오류: 봇의 역할 권한이 부족합니다. 봇 역할을 관리자보다 위에 두거나, 관리자 권한을 부여해 주세요.',
                    ephemeral=True
                )
                return
        else:
            print(f"⚠️ 오류: '{AUTH_ROLE_NAME}' 역할을 서버에서 찾을 수 없습니다.")

        # 2. 닉네임 변경
        try:
            if user.id != guild.owner_id:
                await user.edit(nick=final_nickname)
        except discord.Forbidden:
            print("❌ 오류: 닉네임 변경 권한이 부족합니다.")
        except Exception as e:
            print(f"닉네임 변경 중 기타 오류 발생: {e}")

        # 3. DM 메시지 발송 🎁
        dm_message = f"""
        **서버 인증에 성공하셨습니다 {entered_nickname}님!**
        
        2개월간 즐겁게 즐겨주시기를 바랍니다!
        
        **꼭 우승하고 문화상품권 받아가세요!** 🏆
        
        ---
        
        **[서버 정보 요약]**
        - **서버 주소:** `dogonline.kro.kr`
        - **운영 기간:** 2개월간 운영 (도스온라인 오픈 시 서비스 종료)
        """
        try:
            await user.send(dm_message)
        except discord.Forbidden:
            print(f"❌ 오류: {user.name} 님에게 DM 발송 실패 (DM 수신 차단됨).")

        # 4. 최종 메시지 전송 (followup.send 사용)
        embed_log = discord.Embed(
            title="✅ 인증 완료 및 닉네임 변경",
            color=discord.Color.green()
        )
        embed_log.add_field(name="인증 유저", value=user.mention, inline=True)
        embed_log.add_field(name="새 닉네임", value=final_nickname, inline=True)
        embed_log.add_field(name="참여 목적", value=str(self.purpose), inline=False)

        await interaction.followup.send(
            f'🎉 **{final_nickname}**님, 인증이 완료되었습니다! DM을 확인해주세요.',
            embed=embed_log,
            ephemeral=True
        )


# --- 뷰 (View) 클래스 정의: 버튼 컨테이너 ---
class VerificationView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🔑 유저 인증하기", style=ButtonStyle.primary, custom_id="persistent_verify_button")
    async def verify_button_callback(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(VerificationModal())


#############################################################################
## 🤖 봇 이벤트 및 명령어 부분
#############################################################################

@bot.event
async def on_ready():
    print("-------------------------------------------------------------------")
    print(f'🤖 로그인 성공: {bot.user} 님이 디스코드에 연결되었습니다!')
    bot.add_view(VerificationView()) # 봇이 재시작되어도 인증 버튼이 계속 작동하도록 추가
    print(f"🔑 영구 인증 버튼 활성화 완료!")
    print(f"🚨 신고 API 엔드포인트: http://<봇_실행_서버_IP>:5000/report")
    print(f"🎙️ 음성 채널({TARGET_VOICE_CHANNEL_ID}) 감지 시작 완료!") # [추가] 로그
    print("-------------------------------------------------------------------")


# --- [추가] 음성 채널 입장/퇴장 감지 이벤트 ---
@bot.event
async def on_voice_state_update(member, before, after):
    """유저가 음성 채널에 입장/퇴장/이동할 때마다 실행됩니다."""
    
    # 봇 자신이 변경된 경우는 무시
    if member.bot:
        return

    # 필요한 역할 객체를 서버에서 찾기
    guild = member.guild
    role_to_give = guild.get_role(TARGET_ROLE_ID)

    if not role_to_give:
        # 봇 실행 시 처음에만 로그를 남기고, 계속 남기지는 않도록 간단히 처리
        if not hasattr(bot, '_role_warning_sent'):
            print(f"❌ [음성채널] 오류: ID {TARGET_ROLE_ID}에 해당하는 역할을 찾을 수 없습니다.")
            bot._role_warning_sent = True # 경고 메시지는 한 번만 출력
        return

    # --- 역할 부여 로직 ---
    # 1. 유저가 타겟 음성 채널에 "접속"했거나 "이동"해 온 경우
    if after.channel and after.channel.id == TARGET_VOICE_CHANNEL_ID:
        # 2. 유저가 해당 채널에 "이전"에는 없었는지 확인 (중복 부여 방지)
        if not before.channel or before.channel.id != TARGET_VOICE_CHANNEL_ID:
            try:
                await member.add_roles(role_to_give, reason="타겟 음성 채널 접속")
                print(f"🎙️ [음성채널] {member.name}에게 '{role_to_give.name}' 역할을 부여했습니다.")
            except Exception as e:
                print(f"❌ [음성채널] {member.name}에게 역할 부여 실패: {e}")

    # --- 역할 제거 로직 ---
    # 1. 유저가 타겟 음성 채널에서 "퇴장"했거나 "이동"해 나간 경우
    elif before.channel and before.channel.id == TARGET_VOICE_CHANNEL_ID:
        # 2. 유저가 "현재"는 해당 채널에 없는지 확인
        if not after.channel or after.channel.id != TARGET_VOICE_CHANNEL_ID:
            try:
                await member.remove_roles(role_to_give, reason="타겟 음성 채널 퇴장")
                print(f"🎙️ [음성채널] {member.name}에게서 '{role_to_give.name}' 역할을 제거했습니다.")
            except Exception as e:
                print(f"❌ [음성채널] {member.name}에게서 역할 제거 실패: {e}")
# ----------------------------------------------------


# 일반 명령어 (!안녕, !서버정보)
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # 1. "!안녕" 명령
    if message.content == '!안녕':
        await message.channel.send('반가워요!')

    # 2. "!서버정보" 명령
    if message.content == '!서버정보':
        embed = discord.Embed(
            title="🐶 도그온라인 서버 관련 정보 모음 💬",
            description="도그온라인에 오신 것을 진심으로 환영합니다. 아래 서버 주소 및 중요 정보를 확인해주세요.",
            color=0x8b4513
        )
        embed.add_field(name="마인크래프트 도그온라인 서버 주소 :", value="```dogonline.kro.kr```", inline=False)
        embed.add_field(
            name="✨ 서버 운영 정책 및 이벤트 안내",
            value="""
            > **운영 기간:** 도그온라인은 **2개월**간 운영될 서버입니다.
            > **서비스 종료:** 도스온라인이 열리면 도그온라인은 그 즉시 서비스 종료를 할 것입니다.
            
            \n**🏆 최종 3인 문화상품권 이벤트**
            2개월간 진행되었던 현실경제에서 플레이 해왔던 유저들을 대상으로 탐색을 시작하여 최종 3인에게 문화상품권을 드립니다. 문화상품권의 가격은 추후에 공지로 확인해주시기 바랍니다.
            """,
            inline=False
        )
        embed.add_field(
            name="🔗 공식 커뮤니티 링크",
            value="""
            **디스코드:** [공식 디스코드 바로가기](https://discord.gg/pVpXRXfj)
            **카페:** [공식 카페 바로가기](https://cafe.naver.com/dogdogonline)
            """,
            inline=False
        )
        await message.channel.send(embed=embed)

    await bot.process_commands(message)


# --- 관리자 명령어: 인증 버튼 게시 (!인증설정) ---
@bot.command(name='인증설정')
@commands.has_permissions(administrator=True)
async def setup_verify_button(ctx):
    """관리자가 !인증설정 명령어를 입력하면 인증 버튼을 게시합니다."""
    embed = discord.Embed(
        title="🔑 도그온라인 유저 인증",
        description="서버 활동을 시작하려면 아래 **'유저 인증하기'** 버튼을 눌러 마인크F래프트 닉네임과 참여 목적을 제출해주세요. 인증 완료 시 닉네임이 **[ 시민 ] 닉네임**으로 변경되고 **인증** 역할이 부여됩니다.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=VerificationView())
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        print("❌ 오류: 봇에게 메시지 삭제 권한(Manage Messages)이 없습니다. 수동으로 삭제해야 합니다.")

@setup_verify_button.error
async def setup_verify_button_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ 이 명령어는 **관리자(Administrator)**만 사용할 수 있습니다.", delete_after=5)


#############################################################################
## 🚀 봇 및 웹 서버 실행 부분
#############################################################################

def run_flask():
    # host='0.0.0.0'으로 설정해야 외부(마인크래프트 서버)에서 접속 가능
    flask_app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    # 별도의 스레드에서 Flask 웹 서버 실행
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # 메인 스레드에서 디스코드 봇 실행
    bot.run(TOKEN)