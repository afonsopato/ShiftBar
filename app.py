import streamlit as st
import sqlite3
import pandas as pd
import datetime
import calendar
import holidays
import io
import math

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sick渋谷 - Shift Manager", page_icon="🍻", layout="wide")

# --- 2. BANCO DE DADOS ---
def criar_banco_de_dados():
    conn = sqlite3.connect('bar_dados.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS funcionarios (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT UNIQUE, nome TEXT NOT NULL, nivel TEXT NOT NULL, role TEXT DEFAULT 'staff', senha TEXT NOT NULL, primeiro_acesso INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS disponibilidades (id INTEGER PRIMARY KEY AUTOINCREMENT, funcionario_id INTEGER, data TEXT NOT NULL, status TEXT NOT NULL, hora_inicio TEXT, hora_fim TEXT, UNIQUE(funcionario_id, data))''')
    cursor.execute("SELECT COUNT(*) FROM funcionarios")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO funcionarios (codigo, nome, nivel, role, senha, primeiro_acesso) VALUES ('admin', 'Gerente Master', 'Veteran', 'manager', 'sick1234', 1)")
        cursor.execute("INSERT INTO funcionarios (codigo, nome, nivel, role, senha, primeiro_acesso) VALUES ('tester', 'Conta de Teste', 'Normal', 'tester', 'tester', 0)")
    conn.commit()
    conn.close()

criar_banco_de_dados()

# --- FUNÇÕES DE TEMPO E LÓGICA ---
def get_horarios_permitidos(data_atual):
    feriados_jp = holidays.JP()
    dia_seguinte = data_atual + datetime.timedelta(days=1)
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

# --- 3. DICIONÁRIO DE IDIOMAS ---
textos = {
    "English": {
        "title": "🍻 Sick渋谷 - Portal", "login_title": "Login", "code": "Code:", "pass": "Password:", "login_btn": "Login", "wrong_login": "❌ Invalid Code/Password.",
        "new_pass_title": "🔒 Change Password", "new_pass": "New Password:", "confirm_pass": "Confirm:", "save_pass": "Update", "pass_error_len": "⚠️ Min 6 chars.", "pass_error_match": "⚠️ Mismatch.", "pass_success": "✅ Updated!",
        "logout": "🚪 Logout", "menu_add_staff": "👥 Manage Staff", "menu_shift": "📝 Shift Form", "menu_view_status": "👀 Submissions", "menu_generate": "⚙️ Generate Shift",
        "add_staff_title": "Staff Management", "staff_name": "Name:", "staff_level": "Level:", "role_label": "Account:", "btn_add": "Create", "staff_created": "✅ Created! Code: **{codigo}**", "reset_pass_title": "Reset Password", "select_staff": "Select:", "btn_reset": "Reset", "reset_success": "✅ Reset for {nome}.",
        "tester_alert": "👁️ View Only Mode.", "col_name": "Name", "col_level": "Level",
        "shift_form_title": "Availability", "sel_month": "Month:", "sel_period": "Period:", "period_1": "1st-15th", "period_2": "16th-End", "day": "Day", "status_avail": "Available", "status_yasumi": "Yasumi", "start_time": "Start:", "end_time": "End:", "btn_submit_shift": "Submit", "shift_success": "✅ Saved!",
        "menu_change_pass": "🔑 Change Password", "change_pass_title": "Change Password", "old_pass": "Current:",
        "view_status_title": "Submissions Status", "status_submitted": "✅ Submitted", "status_pending": "❌ Pending",
        "edit_staff_title": "Edit Staff", "btn_edit": "Save", "edit_success": "✅ Updated!",
        "gen_title": "⚙️ AI Shift Generator", "btn_gen": "Generate Smart Schedule", "btn_download": "📥 Download Excel Matrix",
        "yasumi_label": "Yasumi", "off_label": "Off", "allocated_hours": "📊 Score & Hours", "total_hours": "Total Hours",
        "delete_staff_title": "Delete Staff", "btn_delete": "Delete Permanently", "delete_warning": "⚠️ Deleting a staff member will also erase all their shift availability data.", "delete_success": "✅ Staff deleted successfully."
    },
    "日本語": {
        "title": "🍻 Sick渋谷 - ポータル", "login_title": "ログイン", "code": "コード:", "pass": "パスワード:", "login_btn": "ログイン", "wrong_login": "❌ エラー",
        "new_pass_title": "🔒 パスワード変更", "new_pass": "新しいパスワード:", "confirm_pass": "確認:", "save_pass": "更新", "pass_error_len": "⚠️ 6文字以上", "pass_error_match": "⚠️ 一致しません", "pass_success": "✅ 更新完了",
        "logout": "🚪 ログアウト", "menu_add_staff": "👥 スタッフ管理", "menu_shift": "📝 シフト提出", "menu_view_status": "👀 提出状況", "menu_generate": "⚙️ シフト作成",
        "add_staff_title": "スタッフ管理", "staff_name": "名前:", "staff_level": "レベル:", "role_label": "権限:", "btn_add": "作成", "staff_created": "✅ コード: **{codigo}**", "reset_pass_title": "リセット", "select_staff": "選択:", "btn_reset": "リセット", "reset_success": "✅ 完了 {nome}.",
        "tester_alert": "👁️ 閲覧モード", "col_name": "名前", "col_level": "レベル",
        "shift_form_title": "シフト提出", "sel_month": "月:", "sel_period": "期間:", "period_1": "1日〜15日", "period_2": "16日〜月末", "day": "日", "status_avail": "出勤", "status_yasumi": "休み", "start_time": "開始:", "end_time": "終了:", "btn_submit_shift": "提出", "shift_success": "✅ 保存完了",
        "menu_change_pass": "🔑 パスワード変更", "change_pass_title": "パスワード変更", "old_pass": "現在の:",
        "view_status_title": "提出状況", "status_submitted": "✅ 提出済", "status_pending": "❌ 未提出",
        "edit_staff_title": "編集", "btn_edit": "保存", "edit_success": "✅ 更新完了",
        "gen_title": "⚙️ AIシフト自動作成", "btn_gen": "スマートシフトを作成", "btn_download": "📥 Excelをダウンロード",
        "yasumi_label": "休み", "off_label": "オフ", "allocated_hours": "📊 スコアと時間", "total_hours": "合計時間",
        "delete_staff_title": "スタッフを削除", "btn_delete": "完全に削除", "delete_warning": "⚠️ スタッフを削除すると、その人のシフトデータもすべて消去されます。", "delete_success": "✅ 削除しました。"
    },
    "Português": {
        "title": "🍻 Sick渋谷 - Portal", "login_title": "Login", "code": "Código:", "pass": "Senha:", "login_btn": "Entrar", "wrong_login": "❌ Inválido.",
        "new_pass_title": "🔒 Alterar Senha", "new_pass": "Nova (mín 6):", "confirm_pass": "Confirme:", "save_pass": "Atualizar", "pass_error_len": "⚠️ Mínimo 6.", "pass_error_match": "⚠️ Não coincidem.", "pass_success": "✅ Atualizada!",
        "logout": "🚪 Sair", "menu_add_staff": "👥 Gerenciar Equipe", "menu_shift": "📝 Enviar Escala", "menu_view_status": "👀 Status Envios", "menu_generate": "⚙️ Gerador de Escala",
        "add_staff_title": "Gestão de Equipe", "staff_name": "Nome:", "staff_level": "Nível:", "role_label": "Conta:", "btn_add": "Criar", "staff_created": "✅ Código: **{codigo}**", "reset_pass_title": "Resetar Senha", "select_staff": "Selecione:", "btn_reset": "Resetar", "reset_success": "✅ Resetada {nome}.",
        "tester_alert": "👁️ Modo Visualização", "col_name": "Nome", "col_level": "Nível",
        "shift_form_title": "Sua Disponibilidade", "sel_month": "Mês:", "sel_period": "Período:", "period_1": "Dia 1 ao 15", "period_2": "Dia 16 ao final", "day": "Dia", "status_avail": "Trabalhar", "status_yasumi": "Yasumi", "start_time": "Entrada:", "end_time": "Saída:", "btn_submit_shift": "Enviar", "shift_success": "✅ Salvo!",
        "menu_change_pass": "🔑 Mudar Senha", "change_pass_title": "Mudar Senha", "old_pass": "Atual:",
        "view_status_title": "Status de Envios", "status_submitted": "✅ Enviado", "status_pending": "❌ Pendente",
        "edit_staff_title": "Editar", "btn_edit": "Salvar", "edit_success": "✅ Atualizado!",
        "gen_title": "⚙️ Gerador Inteligente de Escala", "btn_gen": "Processar Escala Justa", "btn_download": "📥 Baixar Planilha Final",
        "yasumi_label": "Yasumi", "off_label": "Folga", "allocated_hours": "📊 Multiplicador e Horas", "total_hours": "Total Alocado",
        "delete_staff_title": "Excluir Funcionário", "btn_delete": "Excluir Permanentemente", "delete_warning": "⚠️ Atenção: Excluir um funcionário apagará permanentemente todos os horários que ele enviou.", "delete_success": "✅ Funcionário excluído com sucesso."
    }
}

if 'idioma' not in st.session_state: st.session_state['idioma'] = 'English'
if 'logado' not in st.session_state: st.session_state['logado'] = False

idioma_selecionado = st.sidebar.radio("Language / 言語 / Idioma", ["English", "日本語", "Português"])
st.session_state['idioma'] = idioma_selecionado
t = textos[st.session_state['idioma']]

# ==========================================
# TELAS DE LOGIN
# ==========================================
if not st.session_state['logado']:
    st.title(t["title"])
    with st.form("form_login"):
        cod_input = st.text_input(t["code"]).strip().lower()
        senha_input = st.text_input(t["pass"], type="password")
        if st.form_submit_button(t["login_btn"]):
            conn = sqlite3.connect('bar_dados.db')
            usuario = conn.cursor().execute("SELECT id, nome, role, primeiro_acesso FROM funcionarios WHERE LOWER(codigo)=? AND senha=?", (cod_input, senha_input)).fetchone()
            conn.close()
            if usuario:
                st.session_state.update({'logado': True, 'user_id': usuario[0], 'user_nome': usuario[1], 'role': usuario[2], 'primeiro_acesso': usuario[3]})
                st.rerun()
            else: st.error(t["wrong_login"])

elif st.session_state['primeiro_acesso'] == 1:
    st.title(t["new_pass_title"])
    with st.form("form_troca_senha"):
        n_senha = st.text_input(t["new_pass"], type="password")
        c_senha = st.text_input(t["confirm_pass"], type="password")
        if st.form_submit_button(t["save_pass"]):
            if len(n_senha) >= 6 and n_senha == c_senha:
                conn = sqlite3.connect('bar_dados.db')
                conn.cursor().execute("UPDATE funcionarios SET senha=?, primeiro_acesso=0 WHERE id=?", (n_senha, st.session_state['user_id']))
                conn.commit()
                conn.close()
                st.session_state['primeiro_acesso'] = 0
                st.rerun()
            else: st.error(t["pass_error_match"] if n_senha != c_senha else t["pass_error_len"])

# ==========================================
# ÁREA LOGADA
# ==========================================
else:
    st.sidebar.title(f"Sick渋谷")
    st.sidebar.write(f"👤 {st.session_state['user_nome']} ({st.session_state['role'].upper()})")
    if st.sidebar.button(t["logout"]):
        st.session_state.clear()
        st.rerun()

    opcoes_menu = [t["menu_shift"]]
    if st.session_state['role'] in ['manager', 'tester']:
        opcoes_menu.extend([t["menu_view_status"], t["menu_generate"], t["menu_add_staff"]])
    if st.session_state['role'] == 'staff':
        opcoes_menu.append(t["menu_change_pass"])

    menu = st.sidebar.radio("Menu", opcoes_menu)

    # ---------------------------------------------------------
    # ABA 1: PAINEL DE TURNOS
    # ---------------------------------------------------------
    if menu == t["menu_shift"]:
        st.title(t["shift_form_title"])
        hoje = datetime.date.today()
        opcoes_mes = [(hoje.replace(day=1) + datetime.timedelta(days=31*i)).replace(day=1) for i in range(3)]
        nomes_meses = [f"{m.strftime('%B %Y')}" for m in opcoes_mes]
        col1, col2 = st.columns(2)
        mes_selecionado_str = col1.selectbox(t["sel_month"], nomes_meses)
        quinzena = col2.radio(t["sel_period"], [t["period_1"], t["period_2"]])
        idx_mes = nomes_meses.index(mes_selecionado_str)
        ano, mes = opcoes_mes[idx_mes].year, opcoes_mes[idx_mes].month
        if quinzena == t["period_1"]: dia_inicio, dia_fim = 1, 15
        else: dia_inicio, dia_fim = 16, calendar.monthrange(ano, mes)[1] 

        st.divider()
        st.write(f"**{mes_selecionado_str} - {quinzena}**")
        respostas = {}
        for dia in range(dia_inicio, dia_fim + 1):
            data_atual = datetime.date(ano, mes, dia)
            nome_dia = data_atual.strftime("%A")
            opcoes_horas = get_horarios_permitidos(data_atual)
            st.markdown(f"### {dia:02d} ({nome_dia}) - *Max: {opcoes_horas[-1]}*")
            c1, c2, c3 = st.columns([1.5, 1, 1])
            status = c1.radio(f"Status - {dia}", [t["status_avail"], t["status_yasumi"]], index=1, key=f"status_{dia}", horizontal=True, label_visibility="collapsed")
            bloquear_horas = (status == t["status_yasumi"])
            hora_in = c2.selectbox(t["start_time"], opcoes_horas, index=0, disabled=bloquear_horas, key=f"in_{dia}")
            hora_out = c3.selectbox(t["end_time"], opcoes_horas, index=len(opcoes_horas)-1, disabled=bloquear_horas, key=f"out_{dia}")
            respostas[dia] = {"data": f"{ano}-{mes:02d}-{dia:02d}", "status": "yasumi" if status == t["status_yasumi"] else "disponivel", "in": "" if status == t["status_yasumi"] else hora_in, "out": "" if status == t["status_yasumi"] else hora_out}
            st.markdown("---")
        if st.button(t["btn_submit_shift"], use_container_width=True):
            if st.session_state['role'] == 'tester': st.error("Testers cannot save data!")
            else:
                conn = sqlite3.connect('bar_dados.db')
                cursor = conn.cursor()
                for dia, info in respostas.items(): cursor.execute('REPLACE INTO disponibilidades (funcionario_id, data, status, hora_inicio, hora_fim) VALUES (?, ?, ?, ?, ?)', (st.session_state['user_id'], info["data"], info["status"], info["in"], info["out"]))
                conn.commit()
                conn.close()
                st.success(t["shift_success"])

    # ---------------------------------------------------------
    # ABA 2: VISUALIZAR STATUS DE ENVIOS 
    # ---------------------------------------------------------
    elif menu == t["menu_view_status"]:
        st.title(t["view_status_title"])
        hoje = datetime.date.today()
        opcoes_mes = [(hoje.replace(day=1) + datetime.timedelta(days=31*i)).replace(day=1) for i in range(3)]
        nomes_meses = [f"{m.strftime('%B %Y')}" for m in opcoes_mes]
        col1, col2 = st.columns(2)
        mes_selecionado_str = col1.selectbox(t["sel_month"], nomes_meses, key="view_mes")
        quinzena = col2.radio(t["sel_period"], [t["period_1"], t["period_2"]], key="view_quinzena")
        idx_mes = nomes_meses.index(mes_selecionado_str)
        ano, mes = opcoes_mes[idx_mes].year, opcoes_mes[idx_mes].month
        if quinzena == t["period_1"]: d_in, d_out = f"{ano}-{mes:02d}-01", f"{ano}-{mes:02d}-15"
        else: d_in, d_out = f"{ano}-{mes:02d}-16", f"{ano}-{mes:02d}-{calendar.monthrange(ano, mes)[1]:02d}"
        st.divider()
        conn = sqlite3.connect('bar_dados.db')
        df_staff = pd.read_sql_query("SELECT id, nome, codigo FROM funcionarios WHERE role IN ('staff', 'manager')", conn)
        df_envios = pd.read_sql_query(f"SELECT funcionario_id, COUNT(*) as dias FROM disponibilidades WHERE data >= '{d_in}' AND data <= '{d_out}' GROUP BY funcionario_id", conn)
        conn.close()
        if not df_staff.empty:
            df_final = pd.merge(df_staff, df_envios, left_on='id', right_on='funcionario_id', how='left')
            df_final['Status'] = df_final['dias'].apply(lambda x: t["status_submitted"] if x > 0 else t["status_pending"])
            st.dataframe(df_final[['codigo', 'nome', 'Status']].rename(columns={'codigo': 'Code', 'nome': t["col_name"]}), hide_index=True, use_container_width=True)

    # ---------------------------------------------------------
    # ABA 3: GERADOR DE ESCALA INTELIGENTE
    # ---------------------------------------------------------
    elif menu == t["menu_generate"]:
        st.title(t["gen_title"])
        hoje = datetime.date.today()
        opcoes_mes = [(hoje.replace(day=1) + datetime.timedelta(days=31*i)).replace(day=1) for i in range(3)]
        nomes_meses = [f"{m.strftime('%B %Y')}" for m in opcoes_mes]
        col1, col2 = st.columns(2)
        mes_selecionado_str = col1.selectbox(t["sel_month"], nomes_meses, key="gen_mes")
        quinzena = col2.radio(t["sel_period"], [t["period_1"], t["period_2"]], key="gen_quinzena")
        
        idx_mes = nomes_meses.index(mes_selecionado_str)
        ano, mes = opcoes_mes[idx_mes].year, opcoes_mes[idx_mes].month
        if quinzena == t["period_1"]: data_inicio_str, data_fim_str = f"{ano}-{mes:02d}-01", f"{ano}-{mes:02d}-15"
        else: data_inicio_str, data_fim_str = f"{ano}-{mes:02d}-16", f"{ano}-{mes:02d}-{calendar.monthrange(ano, mes)[1]:02d}"

        st.divider()

        if st.button(t["btn_gen"], use_container_width=True):
            conn = sqlite3.connect('bar_dados.db')
            df_staff = pd.read_sql_query("SELECT id, nome, nivel FROM funcionarios", conn)
            dict_niveis = dict(zip(df_staff['id'], df_staff['nivel']))
            dict_nomes = dict(zip(df_staff['id'], df_staff['nome']))
            query = f"SELECT * FROM disponibilidades WHERE data >= '{data_inicio_str}' AND data <= '{data_fim_str}'"
            df_disp = pd.read_sql_query(query, conn)
            conn.close()

            if df_disp.empty: st.warning("⚠️ Ninguém enviou horários para este período!")
            else:
                horas_oferecidas = {}
                for _, row in df_disp[df_disp['status'] == 'disponivel'].iterrows():
                    q_slots = len(get_slot_list(row['hora_inicio'], row['hora_fim']))
                    horas_oferecidas[row['funcionario_id']] = horas_oferecidas.get(row['funcionario_id'], 0) + q_slots
                
                multiplicadores = {}
                if horas_oferecidas:
                    h_of = list(horas_oferecidas.values())
                    mean_h = sum(h_of) / len(h_of)
                    variance = sum((x - mean_h) ** 2 for x in h_of) / len(h_of)
                    std_h = math.sqrt(variance)
                    
                    for f_id, h in horas_oferecidas.items():
                        if std_h == 0: m = 0.92
                        else:
                            eff_max = mean_h + (1.5 * std_h)
                            eff_min = mean_h - (1.5 * std_h)
                            h_clamped = max(min(h, eff_max), eff_min)
                            if h_clamped >= mean_h: m = 0.92 + 0.08 * ((h_clamped - mean_h) / (eff_max - mean_h)) if eff_max > mean_h else 0.92
                            else: m = 0.85 + 0.07 * ((h_clamped - eff_min) / (mean_h - eff_min)) if mean_h > eff_min else 0.85
                        multiplicadores[f_id] = m

                horas_atribuidas = {f_id: 0 for f_id in dict_nomes.keys()}
                matriz_escala = {f_id: {} for f_id in dict_nomes.keys()}
                dias_da_quinzena = sorted(df_disp['data'].unique())
                
                for dia in dias_da_quinzena:
                    disp_dia = df_disp[df_disp['data'] == dia]
                    data_obj = datetime.datetime.strptime(dia, "%Y-%m-%d").date()
                    horarios_do_dia = get_horarios_permitidos(data_obj)
                    
                    trabalhando_no_slot = {t: [] for t in horarios_do_dia}
                    slots_atribuidos_no_dia = {f_id: [] for f_id in dict_nomes.keys()}
                    
                    for _, row in disp_dia[disp_dia['status'] == 'yasumi'].iterrows():
                        matriz_escala[row['funcionario_id']][dia] = t["yasumi_label"]
                        
                    disp_trabalho = disp_dia[disp_dia['status'] == 'disponivel']
                    
                    livre_no_slot = {t: [] for t in horarios_do_dia}
                    for _, row in disp_trabalho.iterrows():
                        seus_slots = get_slot_list(row['hora_inicio'], row['hora_fim'])
                        for s in seus_slots:
                            if s in livre_no_slot: livre_no_slot[s].append(row['funcionario_id'])

                    for i, slot_atual in enumerate(horarios_do_dia):
                        livres_agora = livre_no_slot[slot_atual]
                        target = 1 if slot_atual == "18:30" else 3 
                        selecionados = []
                        
                        def check_seguranca(lista_ids):
                            vets = sum(1 for f in lista_ids if dict_niveis[f] == 'Veteran')
                            norms = sum(1 for f in lista_ids if dict_niveis[f] == 'Normal')
                            return (vets >= 1) or (norms >= 2)
                        
                        slot_anterior = horarios_do_dia[i-1] if i > 0 else None
                        se_trabalhava_antes = trabalhando_no_slot[slot_anterior] if slot_anterior else []
                        for f in se_trabalhava_antes:
                            if f in livres_agora and len(selecionados) < target: selecionados.append(f)
                                
                        if len(selecionados) < target:
                            candidatos = [f for f in livres_agora if f not in selecionados]
                            if slot_atual == "18:30": candidatos = [f for f in candidatos if dict_niveis[f] in ['Veteran', 'Normal']]
                            seguranca_ok = check_seguranca(selecionados)
                            
                            candidatos.sort(key=lambda x: (
                                1 if (not seguranca_ok and check_seguranca(selecionados + [x])) else 0, 
                                -(horas_atribuidas.get(x, 0) / multiplicadores.get(x, 1.0)), 
                                horas_oferecidas.get(x, 0)   
                            ), reverse=True)
                            
                            for c in candidatos:
                                if len(selecionados) < target:
                                    selecionados.append(c)
                                    seguranca_ok = check_seguranca(selecionados)
                        
                        if slot_atual >= "19:00" and len(selecionados) > 0 and not check_seguranca(selecionados):
                            rookies_selecionados = [f for f in selecionados if dict_niveis[f] == 'Rookie']
                            salvadores = [f for f in livres_agora if f not in selecionados and dict_niveis[f] in ['Veteran', 'Normal']]
                            salvadores.sort(key=lambda x: horas_atribuidas.get(x, 0) / multiplicadores.get(x, 1.0)) 
                            if rookies_selecionados and salvadores:
                                selecionados.remove(rookies_selecionados[0])
                                selecionados.append(salvadores[0])
                                
                        trabalhando_no_slot[slot_atual] = selecionados
                        for f in selecionados:
                            slots_atribuidos_no_dia[f].append(slot_atual)
                            horas_atribuidas[f] += 1 
                            
                    for f_id, slots in slots_atribuidos_no_dia.items():
                        if len(slots) > 0: matriz_escala[f_id][dia] = f"{slots[0]} - {add_30_mins(slots[-1])}"
                        elif f_id in disp_trabalho['funcionario_id'].values:
                            if matriz_escala[f_id].get(dia) != t["yasumi_label"]: matriz_escala[f_id][dia] = t["off_label"]

                df_pivot = pd.DataFrame(matriz_escala).T
                df_pivot.reset_index(inplace=True)
                df_pivot.rename(columns={'index': 'id'}, inplace=True)
                
                df_final = pd.merge(df_staff[['id', 'nome', 'nivel']], df_pivot, on='id', how='right')
                df_final.drop(columns=['id'], inplace=True)
                df_final.rename(columns={'nome': t["col_name"], 'nivel': t["col_level"]}, inplace=True)
                
                for col in df_final.columns:
                    if "20" in col:
                        data_dt = datetime.datetime.strptime(col, "%Y-%m-%d")
                        df_final.rename(columns={col: data_dt.strftime("%d (%a)")}, inplace=True)
                
                df_final = df_final.dropna(thresh=3).fillna("-")
                st.success("✅ " + t["gen_title"] + " Concluído! Sistema Ponderado Ativado.")
                
                col_tabela, col_horas = st.columns([3, 1])
                with col_tabela: st.dataframe(df_final, use_container_width=True)
                with col_horas:
                    st.markdown(f"**{t['allocated_hours']}**")
                    dados_horas = [{"Nome": dict_nomes[f_id], "Mult. (0.85 a 1.0)": round(multiplicadores.get(f_id, 1.0), 3), t["total_hours"]: slots * 0.5} for f_id, slots in horas_atribuidas.items() if f_id in horas_oferecidas]
                    if dados_horas: st.dataframe(pd.DataFrame(dados_horas).sort_values(by="Mult. (0.85 a 1.0)", ascending=False), hide_index=True, use_container_width=True)

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer: df_final.to_excel(writer, index=False, sheet_name='Escala Inteligente')
                st.download_button(label=t["btn_download"], data=buffer.getvalue(), file_name=f"Escala_Sick_{mes_selecionado_str}_{quinzena}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

    # ---------------------------------------------------------
    # ABA 4: GERENCIAR STAFF
    # ---------------------------------------------------------
    elif menu == t["menu_add_staff"]:
        st.title(t["add_staff_title"])
        if st.session_state['role'] == 'tester': st.warning(t["tester_alert"])
        conn = sqlite3.connect('bar_dados.db')
        df = pd.read_sql_query("SELECT id, codigo, nome, nivel, role FROM funcionarios", conn)
        df_show = df[["codigo", "nome", "role"]] if st.session_state['role'] == 'tester' else df[["codigo", "nome", "nivel", "role"]]
        if not df_show.empty: st.dataframe(df_show.rename(columns={"codigo": "Code", "nome": t["col_name"], "nivel": t["col_level"], "role": "Role"}), hide_index=True, use_container_width=True)

        if st.session_state['role'] == 'manager':
            with st.expander("➕ " + t["add_staff_title"]):
                with st.form("form_add"):
                    nome, nivel, tipo_conta = st.text_input(t["staff_name"]), st.selectbox(t["staff_level"], ["Rookie", "Normal", "Veteran"]), st.selectbox(t["role_label"], ["Staff", "Manager"])
                    if st.form_submit_button(t["btn_add"]) and nome != "":
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO funcionarios (codigo, nome, nivel, role, senha, primeiro_acesso) VALUES ('temp', ?, ?, ?, 'sick1234', 1)", (nome, nivel, "manager" if tipo_conta == "Manager" else "staff"))
                        id_novo = cursor.lastrowid
                        cursor.execute("UPDATE funcionarios SET codigo=? WHERE id=?", (f"sk{id_novo:03d}", id_novo))
                        conn.commit()
                        st.success(t["staff_created"].format(codigo=f"sk{id_novo:03d}"))
                        st.rerun()

            if not df.empty:
                with st.expander("✏️ " + t["edit_staff_title"]):
                    opcoes_edit = df['nome'] + " (" + df['codigo'] + ")"
                    sel_edit = st.selectbox(t["select_staff"], opcoes_edit.tolist())
                    idx = opcoes_edit.tolist().index(sel_edit)
                    
                    with st.form("form_edit"):
                        n_nome = st.text_input(t["staff_name"], value=df.iloc[idx]['nome'])
                        n_nivel = st.selectbox(t["staff_level"], ["Rookie", "Normal", "Veteran"], index=["Rookie", "Normal", "Veteran"].index(df.iloc[idx]['nivel']))
                        
                        # A trava mestre de segurança: o ADMIN nunca perde o cargo
                        is_master_admin = (df.iloc[idx]['codigo'] == 'admin')
                        n_tipo = st.selectbox(t["role_label"], ["Staff", "Manager"], index=1 if df.iloc[idx]['role'] == 'manager' else 0, disabled=is_master_admin)
                        
                        if st.form_submit_button(t["btn_edit"]):
                            conn.cursor().execute("UPDATE funcionarios SET nome=?, nivel=?, role=? WHERE id=?", (n_nome, n_nivel, 'manager' if n_tipo == 'Manager' else 'staff', int(df.iloc[idx]['id'])))
                            conn.commit()
                            st.success(t["edit_success"])
                            st.rerun()

            # --- NOVO: EXCLUIR FUNCIONÁRIO ---
            df_delete = df[df['codigo'] != 'admin'] # O Admin nunca aparece na lista de deleção
            if not df_delete.empty:
                with st.expander("🗑️ " + t["delete_staff_title"]):
                    sel_del = st.selectbox(t["select_staff"], (df_delete['nome'] + " (" + df_delete['codigo'] + ")").tolist(), key="del_sel")
                    st.warning(t["delete_warning"])
                    if st.button(t["btn_delete"]):
                        idx_del = (df_delete['nome'] + " (" + df_delete['codigo'] + ")").tolist().index(sel_del)
                        id_alvo = int(df_delete.iloc[idx_del]['id'])
                        conn.cursor().execute("DELETE FROM funcionarios WHERE id=?", (id_alvo,))
                        conn.cursor().execute("DELETE FROM disponibilidades WHERE funcionario_id=?", (id_alvo,))
                        conn.commit()
                        st.success(t["delete_success"])
                        st.rerun()

            df_res = df[df['role'] != 'manager'] 
            if not df_res.empty:
                with st.expander("🔑 " + t["reset_pass_title"]):
                    sel_res = st.selectbox(t["select_staff"], (df_res['nome'] + " (" + df_res['codigo'] + ")").tolist())
                    if st.button(t["btn_reset"]):
                        idx_res = (df_res['nome'] + " (" + df_res['codigo'] + ")").tolist().index(sel_res)
                        conn.cursor().execute("UPDATE funcionarios SET senha='sick1234', primeiro_acesso=1 WHERE id=?", (int(df_res.iloc[idx_res]['id']),))
                        conn.commit()
                        st.success(t["reset_success"].format(nome=df_res.iloc[idx_res]['nome']))
        conn.close()

    # ---------------------------------------------------------
    # ABA 5: MUDAR SENHA (STAFF)
    # ---------------------------------------------------------
    elif menu == t["menu_change_pass"]:
        st.title(t["change_pass_title"])
        with st.form("form_change_pass"):
            s_ant, n_sen, c_sen = st.text_input(t["old_pass"], type="password"), st.text_input(t["new_pass"], type="password"), st.text_input(t["confirm_pass"], type="password")
            if st.form_submit_button(t["save_pass"]):
                conn = sqlite3.connect('bar_dados.db')
                s_bd = conn.cursor().execute("SELECT senha FROM funcionarios WHERE id=?", (st.session_state['user_id'],)).fetchone()[0]
                if s_ant != s_bd: st.error("❌ Erro.")
                elif len(n_sen) < 6 or n_sen != c_sen: st.error("⚠️ Senha inválida.")
                else:
                    conn.cursor().execute("UPDATE funcionarios SET senha=? WHERE id=?", (n_sen, st.session_state['user_id']))
                    conn.commit()
                    st.success(t["pass_success"])
                conn.close()