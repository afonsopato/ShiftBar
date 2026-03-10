import streamlit as st
import psycopg2
import pandas as pd
import datetime
from datetime import timedelta
import calendar
import holidays
import io
import math

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sick渋谷 - Shift Manager", page_icon="🍻", layout="wide")

# --- 2. BANCO DE DADOS (ERP) ---
def get_conn():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def criar_banco_de_dados():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS funcionarios (id SERIAL PRIMARY KEY, codigo VARCHAR UNIQUE, nome VARCHAR NOT NULL, nivel VARCHAR NOT NULL, role VARCHAR DEFAULT 'staff', senha VARCHAR NOT NULL, primeiro_acesso INTEGER DEFAULT 1, is_student INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS disponibilidades (id SERIAL PRIMARY KEY, funcionario_id INTEGER, data VARCHAR NOT NULL, status VARCHAR NOT NULL, hora_inicio VARCHAR, hora_fim VARCHAR, UNIQUE(funcionario_id, data))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS limites_semanais (id SERIAL PRIMARY KEY, funcionario_id INTEGER, quinzena_inicio VARCHAR, limite INTEGER, UNIQUE(funcionario_id, quinzena_inicio))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ferias_estudante (id SERIAL PRIMARY KEY, funcionario_id INTEGER, data_inicio VARCHAR, data_fim VARCHAR, status VARCHAR DEFAULT 'pendente', data_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP, gerente_id INTEGER, data_resposta TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS escala_oficial (id SERIAL PRIMARY KEY, quinzena VARCHAR, data VARCHAR, funcionario_id INTEGER, horario VARCHAR)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS trocas_turno (id SERIAL PRIMARY KEY, turno_id INTEGER, solicitante_id INTEGER, alvo_id INTEGER, tipo VARCHAR, status VARCHAR DEFAULT 'pendente', data_solicitacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP, data_conclusao TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS alertas (id SERIAL PRIMARY KEY, usuario_id INTEGER, mensagem VARCHAR, data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP, lida INTEGER DEFAULT 0)''')
    
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='funcionarios' AND column_name='is_student'")
    if not cursor.fetchone(): cursor.execute("ALTER TABLE funcionarios ADD COLUMN is_student INTEGER DEFAULT 0")
    
    cursor.execute("SELECT COUNT(*) FROM funcionarios")
    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO funcionarios (codigo, nome, nivel, role, senha, primeiro_acesso, is_student) VALUES ('admin', 'Gerente Master', 'Veteran', 'manager', 'sick1234', 1, 0)")
    
    conn.commit()
    cursor.close()
    conn.close()

criar_banco_de_dados()

# --- FUNÇÕES AUXILIARES ---
def get_horarios_permitidos(data_atual):
    feriados_jp = holidays.JP()
    dia_seguinte = data_atual + timedelta(days=1)
    hora_fechamento = 4 if dia_seguinte.weekday() in [5, 6] or dia_seguinte in feriados_jp else 23
    horarios, h, m = [], 18, 30
    while True:
        horarios.append(f"{h:02d}:{m:02d}")
        if hora_fechamento == 23 and h == 23 and m == 0: break
        if hora_fechamento == 4 and h == 4 and m == 0: break
        m += 30
        if m == 60: m, h = 0, h + 1
        if h == 24: h = 0
    return horarios

def str_to_mins(time_str):
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

def get_slot_list(in_str, out_str):
    if not in_str or not out_str: return []
    start = str_to_mins(in_str)
    end = str_to_mins(out_str)
    if end <= start: end += 24 * 60 
    slots, curr = [], start
    while curr < end:
        h, m = (curr // 60) % 24, curr % 60
        slots.append(f"{h:02d}:{m:02d}")
        curr += 30
    return slots

def add_30_mins(time_str):
    h, m = map(int, time_str.split(':'))
    m += 30
    if m == 60: m, h = 0, h + 1
    if h == 24: h = 0
    return f"{h:02d}:{m:02d}"

def calc_horas_str(horario_str):
    if not horario_str or horario_str in ['Folga', 'Yasumi', 'Off', '-']: return 0
    try:
        in_s, out_s = horario_str.split(' - ')
        start, end = str_to_mins(in_s), str_to_mins(out_s)
        if end <= start: end += 24 * 60
        return (end - start) / 60.0
    except: return 0

def add_alerta(user_id, msg):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO alertas (usuario_id, mensagem) VALUES (%s, %s)", (user_id, msg))
    conn.commit()
    cur.close()
    conn.close()

# --- ALERTAS AUTOMÁTICOS (CRON) ---
hoje = datetime.date.today()
if hoje.day == 13: add_alerta(0, "⚠️ Lembrete: O envio da escala da próxima quinzena encerra amanhã (Dia 14) às 23:59!")
if hoje.day == 14: add_alerta(-1, "⚠️ Atenção Gerência: Amanhã começa a nova quinzena. Verifique quem não enviou.")
if hoje.day == 28: add_alerta(0, "⚠️ Lembrete: O envio da escala da próxima quinzena encerra amanhã às 23:59!")

# --- 3. DICIONÁRIO DE IDIOMAS COMPLETO ---
if 'idioma' not in st.session_state: st.session_state['idioma'] = 'Português'
if 'logado' not in st.session_state: st.session_state['logado'] = False

idioma_selecionado = st.sidebar.radio("Language / 言語 / Idioma", ["Português", "English", "日本語"])
st.session_state['idioma'] = idioma_selecionado

textos = {
    "Português": {
        "login_title": "🍻 Sick渋谷 - Portal", "code": "Código:", "pass": "Senha:", "btn_login": "Entrar", "err_login": "❌ Login inválido.",
        "new_pass_title": "🔒 Alterar Senha", "new_pass": "Nova Senha (mín 6):", "conf_pass": "Confirme:", "btn_update_pass": "Atualizar", "err_pass": "⚠️ Senhas curtas ou diferentes.", "success_pass": "✅ Senha atualizada!",
        "menu_shift": "📝 Enviar Escala", "menu_vacation": "🌴 Férias Escolares", "menu_final": "📅 Escala Final", "menu_swap": "🔄 Trocas", "menu_alerts": "🔔 Alertas", "menu_gen": "⚙️ Gerar & Publicar", "menu_history": "📜 Histórico Férias", "menu_staff": "👥 Equipe", "change_pass": "🔑 Mudar Senha", "logout": "🚪 Sair",
        "lbl_month": "Mês:", "lbl_period": "Período:", "p1": "Dia 1 ao 15", "p2": "Dia 16 ao final", "limit_tog": "Limitar horas semanais?", "limit_hrs": "Máximo de horas (Semana):", "conf_zero": "⚠️ Confirmo que NÃO vou trabalhar (0h).", "err_zero": "❌ Marque a confirmação de 0 horas.",
        "status_work": "Trabalhar", "status_yas": "Yasumi (Folga)", "in": "Entrada:", "out": "Saída:", "btn_submit": "Enviar Escala", "msg_saved": "✅ Salvo com sucesso!",
        "vac_info": "Limite sobe de 28h para 40h. **Envie a foto do documento para o gerente!**", "vac_start": "Início:", "vac_end": "Retorno:", "btn_vac": "Lançar Pedido", "msg_vac": "✅ Pedido enviado!",
        "alert_pend": "📋 Aprovações Pendentes", "chk_verify": "Confirmo que verifiquei o documento de", "btn_apr": "Aprovar", "btn_rej": "Recusar", "inbox": "Sua Caixa de Entrada", "btn_read": "Lida", "no_alerts": "Sem novos alertas.",
        "gen_btn": "1. Gerar Rascunho via IA", "gen_edit": "✍️ 2. Edição Manual", "btn_pub": "3. Validar e Publicar", "pub_success": "✅ Escala Publicada!",
        "swap_give": "1. Passar meu Turno", "swap_which": "Qual turno passar?", "swap_type": "Como trocar?", "swap_free": "Livre", "swap_spec": "Pessoa Específica", "swap_who": "Para quem?", "btn_swap_req": "Solicitar Troca",
        "swap_pend": "2. Meus Pedidos", "btn_cancel": "Cancelar", "swap_avail": "3. Assumir Turnos", "btn_accept": "Aceitar",
        "staff_add": "➕ Adicionar", "staff_name": "Nome:", "staff_lvl": "Nível:", "staff_role": "Conta:", "staff_stud": "Estudante (28h)", "btn_create": "Criar",
        "staff_edit": "✏️ Editar", "btn_save": "Salvar", "staff_del": "🗑️ Excluir", "btn_del": "Excluir Permanentemente"
    },
    "English": {
        "login_title": "🍻 Sick渋谷 - Portal", "code": "Code:", "pass": "Password:", "btn_login": "Login", "err_login": "❌ Invalid login.",
        "new_pass_title": "🔒 Change Password", "new_pass": "New Pass (min 6):", "conf_pass": "Confirm:", "btn_update_pass": "Update", "err_pass": "⚠️ Passwords mismatch/too short.", "success_pass": "✅ Password updated!",
        "menu_shift": "📝 Submit Shift", "menu_vacation": "🌴 School Vacation", "menu_final": "📅 Final Schedule", "menu_swap": "🔄 Swaps", "menu_alerts": "🔔 Alerts", "menu_gen": "⚙️ Generate & Publish", "menu_history": "📜 Vacation History", "menu_staff": "👥 Staff", "change_pass": "🔑 Change Password", "logout": "🚪 Logout",
        "lbl_month": "Month:", "lbl_period": "Period:", "p1": "1st to 15th", "p2": "16th to End", "limit_tog": "Limit weekly hours?", "limit_hrs": "Max hours (Week):", "conf_zero": "⚠️ I confirm I will NOT work (0h).", "err_zero": "❌ Please check the 0 hours confirmation.",
        "status_work": "Available", "status_yas": "Yasumi (Off)", "in": "In:", "out": "Out:", "btn_submit": "Submit Shift", "msg_saved": "✅ Saved successfully!",
        "vac_info": "Limit increases to 40h. **Send document photo to manager!**", "vac_start": "Start:", "vac_end": "Return:", "btn_vac": "Request", "msg_vac": "✅ Request sent!",
        "alert_pend": "📋 Pending Approvals", "chk_verify": "I verify the document of", "btn_apr": "Approve", "btn_rej": "Reject", "inbox": "Inbox", "btn_read": "Read", "no_alerts": "No new alerts.",
        "gen_btn": "1. AI Draft Generation", "gen_edit": "✍️ 2. Manual Edit", "btn_pub": "3. Validate & Publish", "pub_success": "✅ Published!",
        "swap_give": "1. Pass my Shift", "swap_which": "Which shift?", "swap_type": "How to swap?", "swap_free": "Free (Anyone)", "swap_spec": "Specific Person", "swap_who": "Who?", "btn_swap_req": "Request Swap",
        "swap_pend": "2. My Requests", "btn_cancel": "Cancel", "swap_avail": "3. Take Shifts", "btn_accept": "Accept",
        "staff_add": "➕ Add", "staff_name": "Name:", "staff_lvl": "Level:", "staff_role": "Account:", "staff_stud": "Student (28h)", "btn_create": "Create",
        "staff_edit": "✏️ Edit", "btn_save": "Save", "staff_del": "🗑️ Delete", "btn_del": "Delete Permanently"
    },
    "日本語": {
        "login_title": "🍻 Sick渋谷 - ポータル", "code": "コード:", "pass": "パスワード:", "btn_login": "ログイン", "err_login": "❌ エラー",
        "new_pass_title": "🔒 パスワード変更", "new_pass": "新しいパスワード:", "conf_pass": "確認:", "btn_update_pass": "更新", "err_pass": "⚠️ 一致しません。", "success_pass": "✅ 更新完了！",
        "menu_shift": "📝 シフト提出", "menu_vacation": "🌴 学校の休暇", "menu_final": "📅 確定シフト", "menu_swap": "🔄 交換", "menu_alerts": "🔔 通知", "menu_gen": "⚙️ シフト作成", "menu_history": "📜 休暇履歴", "menu_staff": "👥 スタッフ", "change_pass": "🔑 PW変更", "logout": "🚪 ログアウト",
        "lbl_month": "月:", "lbl_period": "期間:", "p1": "1日〜15日", "p2": "16日〜月末", "limit_tog": "週の時間を制限?", "limit_hrs": "最大時間 (週):", "conf_zero": "⚠️ 0時間であることを確認しました。", "err_zero": "❌ 0時間の確認にチェックを入れてください。",
        "status_work": "出勤", "status_yas": "休み", "in": "開始:", "out": "終了:", "btn_submit": "提出", "msg_saved": "✅ 保存しました！",
        "vac_info": "上限が40時間に増えます。**マネージャーに書類の写真を送ってください！**", "vac_start": "開始:", "vac_end": "戻る:", "btn_vac": "申請", "msg_vac": "✅ 送信完了！",
        "alert_pend": "📋 承認待ち", "chk_verify": "書類を確認しました: ", "btn_apr": "承認", "btn_rej": "拒否", "inbox": "受信トレイ", "btn_read": "既読", "no_alerts": "新しい通知はありません。",
        "gen_btn": "1. AIシフト作成", "gen_edit": "✍️ 2. 手動編集", "btn_pub": "3. 検証と公開", "pub_success": "✅ 公開完了！",
        "swap_give": "1. シフトを渡す", "swap_which": "どのシフト？", "swap_type": "交換方法は？", "swap_free": "誰でも", "swap_spec": "特定の人", "swap_who": "誰に？", "btn_swap_req": "リクエスト",
        "swap_pend": "2. 保留中のリクエスト", "btn_cancel": "キャンセル", "swap_avail": "3. シフトを受ける", "btn_accept": "承諾",
        "staff_add": "➕ 追加", "staff_name": "名前:", "staff_lvl": "レベル:", "staff_role": "権限:", "staff_stud": "学生 (28h)", "btn_create": "作成",
        "staff_edit": "✏️ 編集", "btn_save": "保存", "staff_del": "🗑️ 削除", "btn_del": "完全に削除"
    }
}
t = textos[st.session_state['idioma']]

# --- 4. ROTEAMENTO E LOGIN ---
if not st.session_state['logado']:
    st.title(t["login_title"])
    with st.form("login"):
        cod, sen = st.text_input(t["code"]).strip().lower(), st.text_input(t["pass"], type="password")
        if st.form_submit_button(t["btn_login"]):
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id, nome, role, is_student, primeiro_acesso FROM funcionarios WHERE LOWER(codigo)=%s AND senha=%s", (cod, sen))
            user = cur.fetchone()
            cur.close()
            conn.close()
            if user:
                st.session_state.update({'logado': True, 'user_id': user[0], 'user_nome': user[1], 'role': user[2], 'is_student': user[3], 'primeiro_acesso': user[4]})
                st.rerun()
            else: st.error(t["err_login"])

elif st.session_state['primeiro_acesso'] == 1:
    st.title(t["new_pass_title"])
    with st.form("form_troca_senha"):
        n_senha, c_senha = st.text_input(t["new_pass"], type="password"), st.text_input(t["conf_pass"], type="password")
        if st.form_submit_button(t["btn_update_pass"]):
            if len(n_senha) >= 6 and n_senha == c_senha:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("UPDATE funcionarios SET senha=%s, primeiro_acesso=0 WHERE id=%s", (n_senha, st.session_state['user_id']))
                conn.commit()
                cur.close()
                conn.close()
                st.session_state['primeiro_acesso'] = 0
                st.rerun()
            else: st.error(t["err_pass"])

else:
    st.sidebar.title(f"Sick渋谷 | 👤 {st.session_state['user_nome']}")
    if st.sidebar.button(t["logout"]):
        st.session_state.clear()
        st.rerun()

    menus = [t["menu_alerts"], t["menu_final"], t["menu_swap"]]
    if st.session_state['role'] in ['manager', 'tester']: 
        menus.extend([t["menu_gen"], t["menu_history"], t["menu_staff"]])
    if st.session_state['role'] == 'staff': 
        menus.insert(0, t["menu_shift"])
        if st.session_state.get('is_student') == 1: menus.insert(1, t["menu_vacation"])
        menus.append(t["change_pass"])
    
    aba = st.sidebar.radio("Menu", menus)

    # =========================================================
    # ABA 1: ENVIAR ESCALA
    # =========================================================
    if aba == t["menu_shift"]:
        st.title(t["menu_shift"])
        opcoes_mes = [(hoje.replace(day=1) + timedelta(days=31*i)).replace(day=1) for i in range(3)]
        nomes_meses = [f"{m.strftime('%B %Y')}" for m in opcoes_mes]
        col1, col2 = st.columns(2)
        mes_selecionado_str = col1.selectbox(t["lbl_month"], nomes_meses)
        quinzena = col2.radio(t["lbl_period"], [t["p1"], t["p2"]])
        
        idx_mes = nomes_meses.index(mes_selecionado_str)
        ano, mes = opcoes_mes[idx_mes].year, opcoes_mes[idx_mes].month
        if quinzena == t["p1"]: dia_inicio, dia_fim = 1, 15
        else: dia_inicio, dia_fim = 16, calendar.monthrange(ano, mes)[1] 
        data_inicio_str = f"{ano}-{mes:02d}-{dia_inicio:02d}"

        st.divider()
        is_stud = (st.session_state.get('is_student', 0) == 1)
        st.markdown(f"### ⏱️ {t['limit_tog']}")
        limite_ativo = st.toggle(t["limit_tog"], value=True if is_stud else False, disabled=is_stud)
        limite_horas = None
        confirma_zero = False
        if limite_ativo:
            limite_horas = st.number_input(t["limit_hrs"], min_value=0, max_value=28 if is_stud else 48, value=0, step=1)
            if limite_horas == 0: confirma_zero = st.checkbox(t["conf_zero"])
        st.divider()

        respostas = {}
        for dia in range(dia_inicio, dia_fim + 1):
            data_atual = datetime.date(ano, mes, dia)
            opcoes_horas = get_horarios_permitidos(data_atual)
            st.markdown(f"### {data_atual.strftime('%d (%A)')} - *Max: {opcoes_horas[-1]}*")
            c1, c2, c3 = st.columns([1.5, 1, 1])
            status = c1.radio(f"Status - {dia}", [t["status_work"], t["status_yas"]], index=1, key=f"status_{dia}", horizontal=True, label_visibility="collapsed")
            bloquear = (status == t["status_yas"])
            hora_in = c2.selectbox(t["in"], opcoes_horas, index=0, disabled=bloquear, key=f"in_{dia}")
            hora_out = c3.selectbox(t["out"], opcoes_horas, index=len(opcoes_horas)-1, disabled=bloquear, key=f"out_{dia}")
            respostas[dia] = {"data": f"{ano}-{mes:02d}-{dia:02d}", "status": "yasumi" if bloquear else "disponivel", "in": "" if bloquear else hora_in, "out": "" if bloquear else hora_out}
            st.markdown("---")
            
        if st.button(t["btn_submit"], use_container_width=True):
            if limite_ativo and limite_horas == 0 and not confirma_zero: st.error(t["err_zero"])
            else:
                conn = get_conn()
                cur = conn.cursor()
                if limite_ativo: cur.execute('''INSERT INTO limites_semanais (funcionario_id, quinzena_inicio, limite) VALUES (%s, %s, %s) ON CONFLICT (funcionario_id, quinzena_inicio) DO UPDATE SET limite = EXCLUDED.limite''', (st.session_state['user_id'], data_inicio_str, limite_horas))
                else: cur.execute("DELETE FROM limites_semanais WHERE funcionario_id=%s AND quinzena_inicio=%s", (st.session_state['user_id'], data_inicio_str))
                for dia, info in respostas.items(): cur.execute('''INSERT INTO disponibilidades (funcionario_id, data, status, hora_inicio, hora_fim) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (funcionario_id, data) DO UPDATE SET status = EXCLUDED.status, hora_inicio = EXCLUDED.hora_inicio, hora_fim = EXCLUDED.hora_fim''', (st.session_state['user_id'], info["data"], info["status"], info["in"], info["out"]))
                conn.commit()
                cur.close()
                conn.close()
                st.success(t["msg_saved"])

    # =========================================================
    # ABA 2: FÉRIAS ESCOLARES
    # =========================================================
    elif aba == t["menu_vacation"]:
        st.title(t["menu_vacation"])
        st.info(t["vac_info"])
        with st.form("form_ferias"):
            d_inicio, d_fim = st.date_input(t["vac_start"]), st.date_input(t["vac_end"])
            if st.form_submit_button(t["btn_vac"]):
                conn = get_conn()
                conn.cursor().execute("INSERT INTO ferias_estudante (funcionario_id, data_inicio, data_fim) VALUES (%s, %s, %s)", (st.session_state['user_id'], str(d_inicio), str(d_fim)))
                conn.commit()
                add_alerta(-1, f"🔔 {st.session_state['user_nome']} pediu férias.")
                st.success(t["msg_vac"])
                conn.close()

    # =========================================================
    # ABA 3: ALERTAS E CAIXA DE ENTRADA
    # =========================================================
    elif aba == t["menu_alerts"]:
        st.title(t["menu_alerts"])
        conn = get_conn()
        if st.session_state['role'] in ['manager', 'tester']:
            st.subheader(t["alert_pend"])
            df_ferias = pd.read_sql_query("SELECT f.id, fun.nome, f.data_inicio, f.data_fim, f.funcionario_id FROM ferias_estudante f JOIN funcionarios fun ON f.funcionario_id = fun.id WHERE f.status='pendente'", conn)
            if not df_ferias.empty:
                for idx, row in df_ferias.iterrows():
                    st.write(f"**{row['nome']}**: {row['data_inicio']} a {row['data_fim']}")
                    veri = st.checkbox(f"{t['chk_verify']} {row['nome']}.", key=f"chk_{row['id']}")
                    c1, c2 = st.columns([1, 5])
                    if c1.button(t["btn_apr"], key=f"apr_{row['id']}"):
                        if veri:
                            cur = conn.cursor()
                            cur.execute("UPDATE ferias_estudante SET status='aprovado', gerente_id=%s, data_resposta=CURRENT_TIMESTAMP WHERE id=%s", (st.session_state['user_id'], row['id']))
                            conn.commit()
                            add_alerta(row['funcionario_id'], "✅ Férias aprovadas!")
                            st.rerun()
                        else: st.error("❌")
                    if c2.button(t["btn_rej"], key=f"rec_{row['id']}"):
                        cur = conn.cursor()
                        cur.execute("UPDATE ferias_estudante SET status='rejeitado', gerente_id=%s, data_resposta=CURRENT_TIMESTAMP WHERE id=%s", (st.session_state['user_id'], row['id']))
                        conn.commit()
                        add_alerta(row['funcionario_id'], "❌ Férias negadas.")
                        st.rerun()
                    st.divider()
            else: st.info("-")
            
        st.subheader(t["inbox"])
        q_user = 0 if st.session_state['role'] == 'staff' else -1
        cur = conn.cursor()
        cur.execute("SELECT id, mensagem, data_criacao FROM alertas WHERE usuario_id IN (%s, %s, %s) AND lida=0 ORDER BY id DESC", (st.session_state['user_id'], 0, q_user))
        alertas = cur.fetchall()
        if alertas:
            for a in alertas:
                c1, c2 = st.columns([4, 1])
                c1.warning(f"[{a[2].strftime('%d/%m %H:%M')}] {a[1]}")
                if c2.button(t["btn_read"], key=f"l_{a[0]}"):
                    cur.execute("UPDATE alertas SET lida=1 WHERE id=%s", (a[0],))
                    conn.commit()
                    st.rerun()
        else: st.success(t["no_alerts"])
        conn.close()

    # =========================================================
    # ABA 4: HISTÓRICO FÉRIAS
    # =========================================================
    elif aba == t["menu_history"] and st.session_state['role'] in ['manager', 'tester']:
        st.title(t["menu_history"])
        df_h = pd.read_sql_query("SELECT fun.nome as Estudante, f.data_pedido as Pedido, f.data_inicio as Início, f.data_fim as Fim, f.status as Status, ger.nome as Gerente FROM ferias_estudante f JOIN funcionarios fun ON f.funcionario_id = fun.id LEFT JOIN funcionarios ger ON f.gerente_id = ger.id ORDER BY f.id DESC", get_conn())
        st.dataframe(df_h, use_container_width=True, hide_index=True)

    # =========================================================
    # ABA 5: O CÉREBRO: GERAR & PUBLICAR (A IA + A MALHA FINA)
    # =========================================================
    elif aba == t["menu_gen"] and st.session_state['role'] in ['manager', 'tester']:
        st.title(t["menu_gen"])
        opcoes_mes = [(hoje.replace(day=1) + timedelta(days=31*i)).replace(day=1) for i in range(3)]
        nomes_meses = [f"{m.strftime('%B %Y')}" for m in opcoes_mes]
        col1, col2 = st.columns(2)
        mes_selecionado_str = col1.selectbox(t["lbl_month"], nomes_meses, key="gen_mes")
        quinzena = col2.radio(t["lbl_period"], [t["p1"], t["p2"]], key="gen_quinzena")
        
        idx_mes = nomes_meses.index(mes_selecionado_str)
        ano, mes = opcoes_mes[idx_mes].year, opcoes_mes[idx_mes].month
        if quinzena == t["p1"]: data_inicio_str, data_fim_str = f"{ano}-{mes:02d}-01", f"{ano}-{mes:02d}-15"
        else: data_inicio_str, data_fim_str = f"{ano}-{mes:02d}-16", f"{ano}-{mes:02d}-{calendar.monthrange(ano, mes)[1]:02d}"

        conn = get_conn()
        df_staff = pd.read_sql_query("SELECT id, nome, nivel, is_student FROM funcionarios", conn)
        dict_niveis = dict(zip(df_staff['id'], df_staff['nivel']))
        dict_nomes = dict(zip(df_staff['id'], df_staff['nome']))
        df_disp = pd.read_sql_query(f"SELECT * FROM disponibilidades WHERE data >= '{data_inicio_str}' AND data <= '{data_fim_str}'", conn)
        df_limites = pd.read_sql_query(f"SELECT funcionario_id, limite FROM limites_semanais WHERE quinzena_inicio = '{data_inicio_str}'", conn)
        dict_limites = dict(zip(df_limites['funcionario_id'], df_limites['limite']))
        
        # --- A MATEMÁTICA PESADA DA IA ---
        if 'df_final_draft' not in st.session_state: st.session_state['df_final_draft'] = None

        if st.button(t["gen_btn"], use_container_width=True):
            if df_disp.empty: st.warning("Ninguém enviou horários / 提出者がいません / No one submitted.")
            else:
                horas_oferecidas = {}
                for _, row in df_disp[df_disp['status'] == 'disponivel'].iterrows():
                    horas_oferecidas[row['funcionario_id']] = horas_oferecidas.get(row['funcionario_id'], 0) + len(get_slot_list(row['hora_inicio'], row['hora_fim']))
                
                multiplicadores = {}
                if horas_oferecidas:
                    h_of = list(horas_oferecidas.values())
                    mean_h = sum(h_of) / len(h_of)
                    std_h = math.sqrt(sum((x - mean_h) ** 2 for x in h_of) / len(h_of))
                    for f_id, h in horas_oferecidas.items():
                        if std_h == 0: m = 0.92
                        else:
                            e_max, e_min = mean_h + (1.5 * std_h), mean_h - (1.5 * std_h)
                            h_c = max(min(h, e_max), e_min)
                            if h_c >= mean_h: m = 0.92 + 0.08 * ((h_c - mean_h) / (e_max - mean_h)) if e_max > mean_h else 0.92
                            else: m = 0.85 + 0.07 * ((h_c - e_min) / (mean_h - e_min)) if mean_h > e_min else 0.85
                        multiplicadores[f_id] = m

                horas_atribuidas = {f_id: 0 for f_id in dict_nomes.keys()}
                horas_por_semana = {f_id: {} for f_id in dict_nomes.keys()}
                matriz_escala = {f_id: {} for f_id in dict_nomes.keys()}
                dias_da_quinzena = sorted(df_disp['data'].unique())
                
                for dia in dias_da_quinzena:
                    disp_dia = df_disp[df_disp['data'] == dia]
                    data_obj = datetime.datetime.strptime(dia, "%Y-%m-%d").date()
                    week_num = data_obj.isocalendar()[1]
                    horarios_do_dia = get_horarios_permitidos(data_obj)
                    
                    trabalhando_no_slot, slots_atr = {tm: [] for tm in horarios_do_dia}, {f_id: [] for f_id in dict_nomes.keys()}
                    for _, r in disp_dia[disp_dia['status'] == 'yasumi'].iterrows(): matriz_escala[r['funcionario_id']][dia] = "Yasumi"
                        
                    disp_trabalho = disp_dia[disp_dia['status'] == 'disponivel']
                    livre_no_slot = {tm: [] for tm in horarios_do_dia}
                    for _, r in disp_trabalho.iterrows():
                        for s in get_slot_list(r['hora_inicio'], r['hora_fim']):
                            if s in livre_no_slot: livre_no_slot[s].append(r['funcionario_id'])

                    for i, slot_atual in enumerate(horarios_do_dia):
                        livres_agora = livre_no_slot[slot_atual]
                        target = 1 if slot_atual == "18:30" else 3 
                        selecionados = []
                        
                        def check_seg(l_ids):
                            return (sum(1 for f in l_ids if dict_niveis[f] == 'Veteran') >= 1) or (sum(1 for f in l_ids if dict_niveis[f] == 'Normal') >= 2)
                        
                        slot_ant = horarios_do_dia[i-1] if i > 0 else None
                        for f in (trabalhando_no_slot[slot_ant] if slot_ant else []):
                            if f in livres_agora and len(selecionados) < target:
                                if horas_por_semana[f].get(week_num, 0) + 0.5 <= dict_limites.get(f, 999): selecionados.append(f)
                                
                        if len(selecionados) < target:
                            candidatos = [f for f in livres_agora if f not in selecionados and horas_por_semana[f].get(week_num, 0) + 0.5 <= dict_limites.get(f, 999)]
                            if slot_atual == "18:30": candidatos = [f for f in candidatos if dict_niveis[f] in ['Veteran', 'Normal']]
                            s_ok = check_seg(selecionados)
                            candidatos.sort(key=lambda x: (1 if (not s_ok and check_seg(selecionados + [x])) else 0, -(horas_atribuidas.get(x, 0) / multiplicadores.get(x, 1.0)), horas_oferecidas.get(x, 0)), reverse=True)
                            for c in candidatos:
                                if len(selecionados) < target:
                                    selecionados.append(c); s_ok = check_seg(selecionados)
                        
                        if slot_atual >= "19:00" and len(selecionados) > 0 and not check_seg(selecionados):
                            rooks = [f for f in selecionados if dict_niveis[f] == 'Rookie']
                            salvs = [f for f in livres_agora if f not in selecionados and dict_niveis[f] in ['Veteran', 'Normal'] and horas_por_semana[f].get(week_num, 0) + 0.5 <= dict_limites.get(f, 999)]
                            salvs.sort(key=lambda x: horas_atribuidas.get(x, 0) / multiplicadores.get(x, 1.0)) 
                            if rooks and salvs:
                                selecionados.remove(rooks[0]); selecionados.append(salvs[0])
                                
                        trabalhando_no_slot[slot_atual] = selecionados
                        for f in selecionados:
                            slots_atr[f].append(slot_atual)
                            horas_atribuidas[f] += 1 
                            horas_por_semana[f][week_num] = horas_por_semana[f].get(week_num, 0) + 0.5
                            
                    for f_id, slots in slots_atr.items():
                        if len(slots) > 0: matriz_escala[f_id][dia] = f"{slots[0]} - {add_30_mins(slots[-1])}"
                        elif f_id in disp_trabalho['funcionario_id'].values:
                            if matriz_escala[f_id].get(dia) != "Yasumi": matriz_escala[f_id][dia] = "Folga"

                df_pivot = pd.DataFrame(matriz_escala).T
                df_pivot.reset_index(inplace=True)
                df_pivot.rename(columns={'index': 'id'}, inplace=True)
                df_final = pd.merge(df_staff[['id', 'nome', 'nivel']], df_pivot, on='id', how='right')
                st.session_state['df_final_draft'] = df_final.dropna(thresh=3).fillna("-")

        # --- O EDITOR DE DADOS ---
        if st.session_state.get('df_final_draft') is not None:
            st.divider()
            st.subheader(t["gen_edit"])
            df_editado = st.data_editor(st.session_state['df_final_draft'], hide_index=True, key="editor_escala")
            
            if st.button(t["btn_pub"], type="primary"):
                erros, avisos = [], []
                df_ferias = pd.read_sql_query("SELECT funcionario_id, data_inicio, data_fim FROM ferias_estudante WHERE status='aprovado'", conn)
                
                for _, row in df_editado.iterrows():
                    f_id = row['id']
                    f_nome = row['nome']
                    is_stud = df_staff[df_staff['id'] == f_id]['is_student'].values[0]
                    limite_voluntario = dict_limites.get(f_id, 999)
                    
                    horas_por_semana_edit = {}
                    for col in df_editado.columns:
                        if "20" in col: 
                            val = row[col]
                            dt_obj = datetime.datetime.strptime(col, "%Y-%m-%d").date()
                            w_num = dt_obj.isocalendar()[1]
                            h_dia = calc_horas_str(val)
                            
                            status_bd = df_disp[(df_disp['funcionario_id'] == f_id) & (df_disp['data'] == col)]['status'].values
                            if len(status_bd) > 0 and status_bd[0] == 'yasumi' and h_dia > 0:
                                avisos.append(f"⚠️ {f_nome}: Escalado em dia de Yasumi ({col})!")
                            
                            horas_por_semana_edit[w_num] = horas_por_semana_edit.get(w_num, 0) + h_dia
                    
                    for w_num, total_h in horas_por_semana_edit.items():
                        if is_stud:
                            tem_ferias = False
                            if not df_ferias[df_ferias['funcionario_id'] == f_id].empty: tem_ferias = True
                            limite_legal = 40 if tem_ferias else 28
                            if total_h > limite_legal: erros.append(f"❌ ERRO/エラー: Estudante {f_nome} > {limite_legal}h (W{w_num}: {total_h}h).")
                        if total_h > limite_voluntario: avisos.append(f"⚠️ {f_nome}: > {limite_voluntario}h (W{w_num}: {total_h}h).")

                if len(erros) > 0:
                    for e in erros: st.error(e)
                    st.stop()
                elif len(avisos) > 0 and not st.session_state.get('confirmar_avisos', False):
                    for a in avisos: st.warning(a)
                    st.checkbox("Confirmo os riscos / リスクを承知しました", key="confirmar_avisos")
                    st.stop()
                else:
                    cur = conn.cursor()
                    for _, row in df_editado.iterrows():
                        f_id = row['id']
                        for col in df_editado.columns:
                            if "20" in col:
                                val = row[col]
                                if val not in ["Folga", "Yasumi", "-", ""]:
                                    cur.execute("INSERT INTO escala_oficial (quinzena, data, funcionario_id, horario) VALUES (%s, %s, %s, %s)", (quinzena, col, f_id, val))
                    conn.commit()
                    add_alerta(0, "📣 Nova Escala Publicada / 新しいシフトが公開されました！")
                    st.success(t["pub_success"])
                    st.session_state['df_final_draft'] = None
                    st.rerun()
        conn.close()

    # =========================================================
    # ABA 6: ESCALA FINAL
    # =========================================================
    elif aba == t["menu_final"]:
        st.title(t["menu_final"])
        conn = get_conn()
        df_oficial = pd.read_sql_query("SELECT o.data, f.nome, o.horario FROM escala_oficial o JOIN funcionarios f ON o.funcionario_id = f.id ORDER BY o.data", conn)
        if df_oficial.empty: st.info("-")
        else:
            df_pivot = df_oficial.pivot(index='nome', columns='data', values='horario').fillna("-")
            st.dataframe(df_pivot, use_container_width=True)
        conn.close()

    # =========================================================
    # ABA 7: MERCADO DE TROCAS
    # =========================================================
    elif aba == t["menu_swap"]:
        st.title(t["menu_swap"])
        conn = get_conn()
        cur = conn.cursor()
        
        st.subheader(t["swap_give"])
        hoje_str = str(datetime.date.today())
        cur.execute("SELECT id, data, horario FROM escala_oficial WHERE funcionario_id=%s AND horario NOT IN ('Folga', 'Yasumi', '-', '') AND data >= %s", (st.session_state['user_id'], hoje_str))
        meus_t = cur.fetchall()
        
        if not meus_t: st.info("-")
        else:
            opcoes_t = [f"{tm[1]} ({tm[2]})" for tm in meus_t]
            t_sel = st.selectbox(t["swap_which"], opcoes_t)
            idx_sel = opcoes_t.index(t_sel)
            id_t_sel, data_t_sel = meus_t[idx_sel][0], meus_t[idx_sel][1]
            
            tipo = st.radio(t["swap_type"], [t["swap_free"], t["swap_spec"]])
            alvo_id = None
            if tipo == t["swap_spec"]:
                cur.execute("SELECT id, nome FROM funcionarios WHERE id != %s", (st.session_state['user_id'],))
                cols = cur.fetchall()
                n_cols = [c[1] for c in cols]
                alvo_nome = st.selectbox(t["swap_who"], n_cols)
                alvo_id = cols[n_cols.index(alvo_nome)][0]
                
            if st.button(t["btn_swap_req"]):
                cur.execute("INSERT INTO trocas_turno (turno_id, solicitante_id, alvo_id, tipo) VALUES (%s, %s, %s, %s)", (id_t_sel, st.session_state['user_id'], alvo_id, tipo))
                conn.commit()
                if alvo_id: add_alerta(alvo_id, f"🔄 {st.session_state['user_nome']}: {data_t_sel}")
                else: add_alerta(0, f"🔄 Turno Aberto / オープンシフト: {data_t_sel} - {st.session_state['user_nome']}")
                st.success("✅")

        st.divider()
        st.subheader(t["swap_pend"])
        cur.execute("SELECT t.id, o.data, o.horario FROM trocas_turno t JOIN escala_oficial o ON t.turno_id = o.id WHERE t.solicitante_id=%s AND t.status='pendente'", (st.session_state['user_id'],))
        pendentes = cur.fetchall()
        if pendentes:
            for p in pendentes:
                c1, c2 = st.columns([3,1])
                c1.write(f"{p[1]} ({p[2]})")
                if c2.button(t["btn_cancel"], key=f"c_{p[0]}"):
                    cur.execute("UPDATE trocas_turno SET status='cancelada' WHERE id=%s", (p[0],))
                    conn.commit(); st.rerun()
        else: st.info("-")

        st.subheader(t["swap_avail"])
        cur.execute("SELECT t.id, o.data, o.horario, f.nome, t.solicitante_id FROM trocas_turno t JOIN escala_oficial o ON t.turno_id = o.id JOIN funcionarios f ON t.solicitante_id = f.id WHERE (t.alvo_id=%s OR t.tipo=%s) AND t.solicitante_id != %s AND t.status='pendente'", (st.session_state['user_id'], t["swap_free"], st.session_state['user_id']))
        disponiveis = cur.fetchall()
        if disponiveis:
            for d in disponiveis:
                c1, c2 = st.columns([3,1])
                c1.write(f"**{d[3]}**: {d[1]} ({d[2]})")
                if c2.button(t["btn_accept"], key=f"a_{d[0]}"):
                    bloqueio = False
                    if st.session_state.get('is_student') == 1:
                        h_add = calc_horas_str(d[2])
                        cur.execute("SELECT id FROM ferias_estudante WHERE funcionario_id=%s AND status='aprovado'", (st.session_state['user_id'],))
                        limite = 40 if cur.fetchone() else 28
                        cur.execute("SELECT horario FROM escala_oficial WHERE funcionario_id=%s", (st.session_state['user_id'],))
                        h_total = sum([calc_horas_str(x[0]) for x in cur.fetchall()])
                        if h_total + h_add > limite:
                            bloqueio = True
                            st.error(f"❌ Limite de {limite}h excedido / 制限時間を超えています.")
                    
                    if not bloqueio:
                        cur.execute("UPDATE trocas_turno SET status='concluida', alvo_id=%s, data_conclusao=CURRENT_TIMESTAMP WHERE id=%s", (st.session_state['user_id'], d[0]))
                        cur.execute("UPDATE escala_oficial SET funcionario_id=%s WHERE id=(SELECT turno_id FROM trocas_turno WHERE id=%s)", (st.session_state['user_id'], d[0]))
                        conn.commit()
                        add_alerta(d[4], f"✅ {st.session_state['user_nome']} aceitou / 承諾しました - {d[1]}.")
                        st.success("✅")
                        st.rerun()
        else: st.info("-")
        conn.close()

    # =========================================================
    # ABA 8: EQUIPE (GERENTES)
    # =========================================================
    elif aba == t["menu_staff"] and st.session_state['role'] in ['manager', 'tester']:
        st.title(t["menu_staff"])
        conn = get_conn()
        df = pd.read_sql_query("SELECT id, codigo, nome, nivel, role, is_student FROM funcionarios", conn)
        st.dataframe(df[["codigo", "nome", "nivel", "role", "is_student"]], hide_index=True, use_container_width=True)

        if st.session_state['role'] == 'manager':
            with st.expander(t["staff_add"]):
                with st.form("form_add"):
                    nome = st.text_input(t["staff_name"])
                    nivel = st.selectbox(t["staff_lvl"], ["Rookie", "Normal", "Veteran"])
                    tipo_conta = st.selectbox(t["staff_role"], ["Staff", "Manager"])
                    is_student_input = st.checkbox(t["staff_stud"])
                    if st.form_submit_button(t["btn_create"]) and nome:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO funcionarios (codigo, nome, nivel, role, senha, primeiro_acesso, is_student) VALUES ('temp', %s, %s, %s, 'sick1234', 1, %s) RETURNING id", (nome, nivel, "manager" if tipo_conta == "Manager" else "staff", 1 if is_student_input else 0))
                        id_novo = cur.fetchone()[0]
                        cur.execute("UPDATE funcionarios SET codigo=%s WHERE id=%s", (f"sk{id_novo:03d}", id_novo))
                        conn.commit()
                        st.success(f"✅ sk{id_novo:03d}")
                        st.rerun()

            with st.expander(t["staff_edit"]):
                if not df.empty:
                    sel = st.selectbox("Selecione:", (df['nome'] + " (" + df['codigo'] + ")").tolist(), key="sel_edit_staff")
                    idx = (df['nome'] + " (" + df['codigo'] + ")").tolist().index(sel)
                    with st.form("form_edit"):
                        n_nome = st.text_input(t["staff_name"], value=df.iloc[idx]['nome'])
                        n_nivel = st.selectbox(t["staff_lvl"], ["Rookie", "Normal", "Veteran"], index=["Rookie", "Normal", "Veteran"].index(df.iloc[idx]['nivel']))
                        n_tipo = st.selectbox(t["staff_role"], ["Staff", "Manager"], index=1 if df.iloc[idx]['role'] == 'manager' else 0, disabled=(df.iloc[idx]['codigo'] == 'admin'))
                        n_student = st.checkbox(t["staff_stud"], value=bool(df.iloc[idx]['is_student']))
                        if st.form_submit_button(t["btn_save"]):
                            cur = conn.cursor()
                            cur.execute("UPDATE funcionarios SET nome=%s, nivel=%s, role=%s, is_student=%s WHERE id=%s", (n_nome, n_nivel, 'manager' if n_tipo == 'Manager' else 'staff', 1 if n_student else 0, int(df.iloc[idx]['id'])))
                            conn.commit()
                            st.success("✅")
                            st.rerun()

            with st.expander(t["staff_del"]):
                df_delete = df[df['codigo'] != 'admin'] 
                if not df_delete.empty:
                    sel_del = st.selectbox("Selecione:", (df_delete['nome'] + " (" + df_delete['codigo'] + ")").tolist(), key="del_sel")
                    if st.button(t["btn_del"]):
                        id_alvo = int(df_delete.iloc[(df_delete['nome'] + " (" + df_delete['codigo'] + ")").tolist().index(sel_del)]['id'])
                        cur = conn.cursor()
                        cur.execute("DELETE FROM funcionarios WHERE id=%s", (id_alvo,))
                        cur.execute("DELETE FROM disponibilidades WHERE funcionario_id=%s", (id_alvo,))
                        conn.commit()
                        st.success("✅")
                        st.rerun()
        conn.close()

    # =========================================================
    # ABA 9: MUDAR SENHA (STAFF)
    # =========================================================
    elif aba == t["change_pass"]:
        st.title(t["change_pass"])
        with st.form("form_change_pass"):
            s_ant = st.text_input("Atual / 現在の:", type="password")
            n_sen = st.text_input("Nova / 新しい (mín 6):", type="password")
            c_sen = st.text_input("Confirme / 確認:", type="password")
            if st.form_submit_button("Salvar / 保存"):
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT senha FROM funcionarios WHERE id=%s", (st.session_state['user_id'],))
                if s_ant != cur.fetchone()[0]: st.error("❌ Erro.")
                elif len(n_sen) < 6 or n_sen != c_sen: st.error("⚠️ Senha inválida.")
                else:
                    cur.execute("UPDATE funcionarios SET senha=%s WHERE id=%s", (n_sen, st.session_state['user_id']))
                    conn.commit()
                    st.success("✅")
                cur.close()
                conn.close()