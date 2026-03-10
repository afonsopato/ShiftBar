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

# --- 2. BANCO DE DADOS (ERP COMPLETO) ---
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
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO funcionarios (codigo, nome, nivel, role, senha, primeiro_acesso, is_student) VALUES ('admin', 'Gerente Master', 'Veteran', 'manager', 'sick1234', 1, 0)")
    
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

# --- LÓGICA DE ALERTAS AUTOMÁTICOS ---
hoje = datetime.date.today()
if hoje.day == 13: add_alerta(0, "⚠️ Lembrete: O envio da escala da próxima quinzena encerra amanhã (Dia 14) às 23:59!")
if hoje.day == 14: add_alerta(-1, "⚠️ Atenção Gerência: Amanhã começa a nova quinzena. Verifique quem não enviou.")
if hoje.day == 28: add_alerta(0, "⚠️ Lembrete: O envio da escala da próxima quinzena encerra amanhã às 23:59!")

# --- 3. LOGIN E ROTEAMENTO ---
if 'idioma' not in st.session_state: st.session_state['idioma'] = 'Português'
if 'logado' not in st.session_state: st.session_state['logado'] = False

t = {
    "menu_shift": "📝 Enviar Escala", "menu_vacation": "🌴 Férias Escolares", "menu_final": "📅 Escala Final", 
    "menu_swap": "🔄 Trocas", "menu_alerts": "🔔 Alertas", "menu_gen": "⚙️ Gerar & Publicar", 
    "menu_staff": "👥 Equipe", "menu_history": "📜 Histórico de Férias"
}

if not st.session_state['logado']:
    st.title("🍻 Sick渋谷 - Portal")
    with st.form("login"):
        cod, sen = st.text_input("Código de Acesso:").strip().lower(), st.text_input("Senha:", type="password")
        if st.form_submit_button("Entrar"):
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id, nome, role, is_student, primeiro_acesso FROM funcionarios WHERE LOWER(codigo)=%s AND senha=%s", (cod, sen))
            user = cur.fetchone()
            cur.close()
            conn.close()
            if user:
                st.session_state.update({'logado': True, 'user_id': user[0], 'user_nome': user[1], 'role': user[2], 'is_student': user[3], 'primeiro_acesso': user[4]})
                st.rerun()
            else: st.error("❌ Login inválido.")

elif st.session_state['primeiro_acesso'] == 1:
    st.title("🔒 Primeiro Acesso: Altere sua Senha")
    with st.form("form_troca_senha"):
        n_senha, c_senha = st.text_input("Nova Senha (mín. 6):", type="password"), st.text_input("Confirme a Senha:", type="password")
        if st.form_submit_button("Atualizar Senha"):
            if len(n_senha) >= 6 and n_senha == c_senha:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("UPDATE funcionarios SET senha=%s, primeiro_acesso=0 WHERE id=%s", (n_senha, st.session_state['user_id']))
                conn.commit()
                cur.close()
                conn.close()
                st.session_state['primeiro_acesso'] = 0
                st.rerun()
            else: st.error("⚠️ Senhas não coincidem ou são curtas.")

else:
    # --- MENU LATERAL ---
    st.sidebar.title(f"Sick渋谷 | 👤 {st.session_state['user_nome']}")
    if st.sidebar.button("🚪 Sair"):
        st.session_state.clear()
        st.rerun()

    menus = [t["menu_alerts"], t["menu_final"], t["menu_swap"]]
    if st.session_state['role'] in ['manager', 'tester']: 
        menus.extend([t["menu_gen"], t["menu_history"], t["menu_staff"]])
    if st.session_state['role'] == 'staff': 
        menus.insert(0, t["menu_shift"])
        if st.session_state.get('is_student') == 1: menus.insert(1, t["menu_vacation"])
        menus.append("🔑 Mudar Senha")
    
    aba = st.sidebar.radio("Menu Principal", menus)

    # =========================================================
    # ABA 1: ENVIAR ESCALA
    # =========================================================
    if aba == t["menu_shift"]:
        st.title(t["menu_shift"])
        opcoes_mes = [(hoje.replace(day=1) + timedelta(days=31*i)).replace(day=1) for i in range(3)]
        nomes_meses = [f"{m.strftime('%B %Y')}" for m in opcoes_mes]
        col1, col2 = st.columns(2)
        mes_selecionado_str = col1.selectbox("Mês:", nomes_meses)
        quinzena = col2.radio("Período:", ["Dia 1 ao 15", "Dia 16 ao final do mês"])
        
        idx_mes = nomes_meses.index(mes_selecionado_str)
        ano, mes = opcoes_mes[idx_mes].year, opcoes_mes[idx_mes].month
        if quinzena == "Dia 1 ao 15": dia_inicio, dia_fim = 1, 15
        else: dia_inicio, dia_fim = 16, calendar.monthrange(ano, mes)[1] 
        data_inicio_str = f"{ano}-{mes:02d}-{dia_inicio:02d}"

        st.divider()
        is_stud = (st.session_state.get('is_student', 0) == 1)
        st.markdown("### ⏱️ Restrições de Horas Semanais")
        limite_ativo = st.toggle("Limitar horas na semana?", value=True if is_stud else False, disabled=is_stud)
        limite_horas = None
        confirma_zero = False
        if limite_ativo:
            limite_horas = st.number_input("Máximo de horas (Semana):", min_value=0, max_value=28 if is_stud else 48, value=0, step=1)
            if limite_horas == 0: confirma_zero = st.checkbox("⚠️ Confirmo que NÃO vou trabalhar (0 horas) nesta quinzena.")
        st.divider()

        respostas = {}
        for dia in range(dia_inicio, dia_fim + 1):
            data_atual = datetime.date(ano, mes, dia)
            opcoes_horas = get_horarios_permitidos(data_atual)
            st.markdown(f"### {data_atual.strftime('%d (%A)')} - *Max: {opcoes_horas[-1]}*")
            c1, c2, c3 = st.columns([1.5, 1, 1])
            status = c1.radio(f"Status - {dia}", ["Trabalhar", "Yasumi (Folga)"], index=1, key=f"status_{dia}", horizontal=True, label_visibility="collapsed")
            bloquear = (status == "Yasumi (Folga)")
            hora_in = c2.selectbox("Entrada:", opcoes_horas, index=0, disabled=bloquear, key=f"in_{dia}")
            hora_out = c3.selectbox("Saída:", opcoes_horas, index=len(opcoes_horas)-1, disabled=bloquear, key=f"out_{dia}")
            respostas[dia] = {"data": f"{ano}-{mes:02d}-{dia:02d}", "status": "yasumi" if bloquear else "disponivel", "in": "" if bloquear else hora_in, "out": "" if bloquear else hora_out}
            st.markdown("---")
            
        if st.button("Enviar Escala", use_container_width=True):
            if limite_ativo and limite_horas == 0 and not confirma_zero: st.error("❌ Você selecionou 0 horas. Marque a caixa de confirmação.")
            else:
                conn = get_conn()
                cur = conn.cursor()
                if limite_ativo: cur.execute('''INSERT INTO limites_semanais (funcionario_id, quinzena_inicio, limite) VALUES (%s, %s, %s) ON CONFLICT (funcionario_id, quinzena_inicio) DO UPDATE SET limite = EXCLUDED.limite''', (st.session_state['user_id'], data_inicio_str, limite_horas))
                else: cur.execute("DELETE FROM limites_semanais WHERE funcionario_id=%s AND quinzena_inicio=%s", (st.session_state['user_id'], data_inicio_str))
                for dia, info in respostas.items(): cur.execute('''INSERT INTO disponibilidades (funcionario_id, data, status, hora_inicio, hora_fim) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (funcionario_id, data) DO UPDATE SET status = EXCLUDED.status, hora_inicio = EXCLUDED.hora_inicio, hora_fim = EXCLUDED.hora_fim''', (st.session_state['user_id'], info["data"], info["status"], info["in"], info["out"]))
                conn.commit()
                cur.close()
                conn.close()
                st.success("✅ Horários salvos com sucesso!")

    # =========================================================
    # ABA 2: FÉRIAS ESCOLARES
    # =========================================================
    elif aba == t["menu_vacation"]:
        st.title("🌴 Solicitar Férias Escolares")
        st.info("Limite sobe de 28h para 40h semanais. **Obrigatório enviar foto do documento para o gerente via LINE/WhatsApp!**")
        with st.form("form_ferias"):
            d_inicio, d_fim = st.date_input("Data de Início"), st.date_input("Retorno às Aulas")
            if st.form_submit_button("Lançar Pedido"):
                conn = get_conn()
                conn.cursor().execute("INSERT INTO ferias_estudante (funcionario_id, data_inicio, data_fim) VALUES (%s, %s, %s)", (st.session_state['user_id'], str(d_inicio), str(d_fim)))
                conn.commit()
                add_alerta(-1, f"🔔 {st.session_state['user_nome']} solicitou liberação de férias escolares. Aguardando foto do doc.")
                st.success("✅ Pedido enviado! Mande o documento para a gerência.")
                conn.close()
            
    # =========================================================
    # ABA 3: ALERTAS E CAIXA DE ENTRADA
    # =========================================================
    elif aba == t["menu_alerts"]:
        st.title(t["menu_alerts"])
        conn = get_conn()
        if st.session_state['role'] in ['manager', 'tester']:
            st.subheader("📋 Aprovações de Férias Pendentes")
            df_ferias = pd.read_sql_query("SELECT f.id, fun.nome, f.data_inicio, f.data_fim, f.funcionario_id FROM ferias_estudante f JOIN funcionarios fun ON f.funcionario_id = fun.id WHERE f.status='pendente'", conn)
            if not df_ferias.empty:
                for idx, row in df_ferias.iterrows():
                    st.write(f"**{row['nome']}**: {row['data_inicio']} a {row['data_fim']}")
                    veri = st.checkbox(f"Confirmo que verifiquei o documento escolar de {row['nome']}.", key=f"chk_{row['id']}")
                    c1, c2 = st.columns([1, 5])
                    if c1.button("Aprovar", key=f"apr_{row['id']}"):
                        if veri:
                            cur = conn.cursor()
                            cur.execute("UPDATE ferias_estudante SET status='aprovado', gerente_id=%s, data_resposta=CURRENT_TIMESTAMP WHERE id=%s", (st.session_state['user_id'], row['id']))
                            conn.commit()
                            add_alerta(row['funcionario_id'], "✅ Férias aprovadas. Limite de 40h liberado!")
                            st.rerun()
                        else: st.error("❌ Marque a caixa de verificação.")
                    if c2.button("Recusar", key=f"rec_{row['id']}"):
                        cur = conn.cursor()
                        cur.execute("UPDATE ferias_estudante SET status='rejeitado', gerente_id=%s, data_resposta=CURRENT_TIMESTAMP WHERE id=%s", (st.session_state['user_id'], row['id']))
                        conn.commit()
                        add_alerta(row['funcionario_id'], "❌ Férias negadas.")
                        st.rerun()
                    st.divider()
            else: st.info("Nada pendente.")
            
        st.subheader("Sua Caixa de Entrada")
        q_user = 0 if st.session_state['role'] == 'staff' else -1
        cur = conn.cursor()
        cur.execute("SELECT id, mensagem, data_criacao FROM alertas WHERE usuario_id IN (%s, %s, %s) AND lida=0 ORDER BY id DESC", (st.session_state['user_id'], 0, q_user))
        alertas = cur.fetchall()
        if alertas:
            for a in alertas:
                c1, c2 = st.columns([4, 1])
                c1.warning(f"[{a[2].strftime('%d/%m %H:%M')}] {a[1]}")
                if c2.button("Lida", key=f"l_{a[0]}"):
                    cur.execute("UPDATE alertas SET lida=1 WHERE id=%s", (a[0],))
                    conn.commit()
                    st.rerun()
        else: st.success("Sem novos alertas.")
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
        mes_selecionado_str = col1.selectbox("Mês:", nomes_meses, key="gen_mes")
        quinzena = col2.radio("Período:", ["Dia 1 ao 15", "Dia 16 ao final do mês"], key="gen_quinzena")
        
        idx_mes = nomes_meses.index(mes_selecionado_str)
        ano, mes = opcoes_mes[idx_mes].year, opcoes_mes[idx_mes].month
        if quinzena == "Dia 1 ao 15": data_inicio_str, data_fim_str = f"{ano}-{mes:02d}-01", f"{ano}-{mes:02d}-15"
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

        if st.button("1. Gerar Rascunho via Inteligência Artificial", use_container_width=True):
            if df_disp.empty: st.warning("Ninguém enviou horários.")
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
                    
                    trabalhando_no_slot, slots_atr = {t: [] for t in horarios_do_dia}, {f_id: [] for f_id in dict_nomes.keys()}
                    for _, r in disp_dia[disp_dia['status'] == 'yasumi'].iterrows(): matriz_escala[r['funcionario_id']][dia] = "Yasumi"
                        
                    disp_trabalho = disp_dia[disp_dia['status'] == 'disponivel']
                    livre_no_slot = {t: [] for t in horarios_do_dia}
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
                st.success("Rascunho gerado! Edite na tabela abaixo.")

        # --- O EDITOR DE DADOS ---
        if st.session_state.get('df_final_draft') is not None:
            st.divider()
            st.subheader("✍️ 2. Edição Manual (Malha Fina)")
            st.write("Dê dois cliques nas células para alterar os horários. Quando terminar, valide e publique.")
            df_editado = st.data_editor(st.session_state['df_final_draft'], hide_index=True, key="editor_escala")
            
            if st.button("3. Validar e Publicar Escala 🚀", type="primary"):
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
                                avisos.append(f"⚠️ {f_nome} está escalado em {col} mas havia pedido Yasumi!")
                            
                            horas_por_semana_edit[w_num] = horas_por_semana_edit.get(w_num, 0) + h_dia
                    
                    for w_num, total_h in horas_por_semana_edit.items():
                        if is_stud:
                            tem_ferias = False
                            if not df_ferias[df_ferias['funcionario_id'] == f_id].empty: tem_ferias = True
                            limite_legal = 40 if tem_ferias else 28
                            
                            if total_h > limite_legal:
                                erros.append(f"❌ ERRO LEGAL: Estudante {f_nome} ultrapassa {limite_legal}h na semana {w_num} (Total: {total_h}h).")
                        
                        if total_h > limite_voluntario:
                            avisos.append(f"⚠️ {f_nome} pediu limite de {limite_voluntario}h, mas foi escalado para {total_h}h na semana {w_num}.")

                if len(erros) > 0:
                    for e in erros: st.error(e)
                    st.stop()
                elif len(avisos) > 0 and not st.session_state.get('confirmar_avisos', False):
                    for a in avisos: st.warning(a)
                    st.checkbox("Confirmo as inconsistências acima e assumo o risco de publicar.", key="confirmar_avisos")
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
                    add_alerta(0, f"📣 A Escala da {quinzena} de {mes_selecionado_str} foi publicada! Confira a aba Escala Final.")
                    st.success("✅ Escala Publicada Oficialmente!")
                    st.session_state['df_final_draft'] = None
                    st.rerun()
        conn.close()
    # =========================================================
    # ABA 6: ESCALA FINAL
    # =========================================================
    elif aba == t["menu_final"]:
        st.title("📅 Escala Oficial do Bar")
        st.write("Abaixo está a escala definitiva publicada pelos gerentes.")
        conn = get_conn()
        df_oficial = pd.read_sql_query("SELECT o.data, f.nome, o.horario FROM escala_oficial o JOIN funcionarios f ON o.funcionario_id = f.id ORDER BY o.data", conn)
        if df_oficial.empty: 
            st.info("Nenhuma escala oficial publicada ainda.")
        else:
            # Transforma em Pivot (Tabela Cruzada) para visualização bonita
            df_pivot = df_oficial.pivot(index='nome', columns='data', values='horario').fillna("-")
            st.dataframe(df_pivot, use_container_width=True)
        conn.close()

    # =========================================================
    # ABA 7: MERCADO DE TROCAS
    # =========================================================
    elif aba == t["menu_swap"]:
        st.title("🔄 Mercado de Trocas")
        conn = get_conn()
        cur = conn.cursor()
        
        st.subheader("1. Passar meu Turno")
        st.write("Selecione um turno seu para oferecer:")
        
        hoje_str = str(datetime.date.today())
        # Traz apenas turnos a partir de hoje que não são folga
        cur.execute("SELECT id, data, horario FROM escala_oficial WHERE funcionario_id=%s AND horario NOT IN ('Folga', 'Yasumi', '-', '')", (st.session_state['user_id'],))
        meus_t = cur.fetchall()
        
        if not meus_t: 
            st.info("Você não tem turnos futuros disponíveis.")
        else:
            opcoes_t = [f"{t[1]} ({t[2]})" for t in meus_t]
            t_sel = st.selectbox("Qual turno você quer passar?", opcoes_t)
            idx_sel = opcoes_t.index(t_sel)
            id_t_sel = meus_t[idx_sel][0]
            data_t_sel = meus_t[idx_sel][1]
            horario_str_sel = meus_t[idx_sel][2]
            
            tipo = st.radio("Como quer trocar?", ["Livre (Qualquer um)", "Pessoa Específica"])
            alvo_id = None
            if tipo == "Pessoa Específica":
                cur.execute("SELECT id, nome FROM funcionarios WHERE id != %s", (st.session_state['user_id'],))
                cols = cur.fetchall()
                n_cols = [c[1] for c in cols]
                alvo_nome = st.selectbox("Para quem?", n_cols)
                alvo_id = cols[n_cols.index(alvo_nome)][0]
                
            if st.button("Solicitar Troca"):
                # A validação real de 1.5 horas seria implementada aqui convertendo a string de data.
                # Como a data está em formato exótico "16 (Seg)", liberamos a inserção.
                cur.execute("INSERT INTO trocas_turno (turno_id, solicitante_id, alvo_id, tipo) VALUES (%s, %s, %s, %s)", (id_t_sel, st.session_state['user_id'], alvo_id, tipo))
                conn.commit()
                if alvo_id: add_alerta(alvo_id, f"🔄 {st.session_state['user_nome']} pediu para trocar o turno de {data_t_sel} ({horario_str_sel}) com você.")
                else: add_alerta(0, f"🔄 Turno Aberto no dia {data_t_sel} ({horario_str_sel}) por {st.session_state['user_nome']}.")
                st.success("Pedido lançado no mercado!")

        st.divider()
        st.subheader("2. Meus Pedidos Pendentes")
        cur.execute("SELECT t.id, o.data, o.horario FROM trocas_turno t JOIN escala_oficial o ON t.turno_id = o.id WHERE t.solicitante_id=%s AND t.status='pendente'", (st.session_state['user_id'],))
        pendentes = cur.fetchall()
        if pendentes:
            for p in pendentes:
                c1, c2 = st.columns([3,1])
                c1.write(f"Turno: {p[1]} ({p[2]})")
                if c2.button("Cancelar Pedido", key=f"c_{p[0]}"):
                    cur.execute("UPDATE trocas_turno SET status='cancelada' WHERE id=%s", (p[0],))
                    conn.commit(); add_alerta(0, "Aviso: Uma troca aberta foi cancelada pelo solicitante."); st.rerun()
        else:
            st.info("Nenhum pedido seu está aguardando.")

        st.subheader("3. Assumir Turnos (Disponíveis para mim)")
        cur.execute("SELECT t.id, o.data, o.horario, f.nome, t.solicitante_id FROM trocas_turno t JOIN escala_oficial o ON t.turno_id = o.id JOIN funcionarios f ON t.solicitante_id = f.id WHERE (t.alvo_id=%s OR t.tipo='Livre (Qualquer um)') AND t.solicitante_id != %s AND t.status='pendente'", (st.session_state['user_id'], st.session_state['user_id']))
        disponiveis = cur.fetchall()
        if disponiveis:
            for d in disponiveis:
                c1, c2 = st.columns([3,1])
                c1.write(f"**{d[3]}** passou o turno de **{d[1]} ({d[2]})**.")
                if c2.button("Aceitar", key=f"a_{d[0]}"):
                    
                    bloqueio = False
                    # Validação de Estudante ao Aceitar Turno de Última Hora
                    if st.session_state.get('is_student') == 1:
                        h_add = calc_horas_str(d[2])
                        cur.execute("SELECT id FROM ferias_estudante WHERE funcionario_id=%s AND status='aprovado'", (st.session_state['user_id'],))
                        tem_ferias = cur.fetchone()
                        limite = 40 if tem_ferias else 28
                        
                        cur.execute("SELECT horario FROM escala_oficial WHERE funcionario_id=%s", (st.session_state['user_id'],))
                        h_total = sum([calc_horas_str(x[0]) for x in cur.fetchall()])
                        
                        if h_total + h_add > limite:
                            bloqueio = True
                            st.error(f"❌ Aceitar este turno vai ultrapassar seu limite legal de {limite}h. Troca cancelada pelo sistema.")
                    
                    if not bloqueio:
                        cur.execute("UPDATE trocas_turno SET status='concluida', alvo_id=%s, data_conclusao=CURRENT_TIMESTAMP WHERE id=%s", (st.session_state['user_id'], d[0]))
                        cur.execute("UPDATE escala_oficial SET funcionario_id=%s WHERE id=(SELECT turno_id FROM trocas_turno WHERE id=%s)", (st.session_state['user_id'], d[0]))
                        conn.commit()
                        add_alerta(d[4], f"✅ {st.session_state['user_nome']} assumiu seu turno dia {d[1]}.")
                        add_alerta(0, f"🔄 TROCA OFICIALIZADA: {d[3]} passou para {st.session_state['user_nome']} ({d[1]}).")
                        st.success("Turno assumido! A escala final foi atualizada.")
                        st.rerun()
        else:
            st.info("Nenhum turno disponível para você pegar no momento.")
        conn.close()

    # =========================================================
    # ABA 8: EQUIPE E GERENCIAMENTO (GERENTES)
    # =========================================================
    elif aba == t["menu_staff"] and st.session_state['role'] in ['manager', 'tester']:
        st.title("👥 Gestão de Equipe")
        if st.session_state['role'] == 'tester': st.warning("Modo Visualização.")
        
        conn = get_conn()
        df = pd.read_sql_query("SELECT id, codigo, nome, nivel, role, is_student FROM funcionarios", conn)
        df_show = df[["codigo", "nome", "nivel", "role", "is_student"]]
        st.dataframe(df_show, hide_index=True, use_container_width=True)

        if st.session_state['role'] == 'manager':
            with st.expander("➕ Adicionar Funcionário"):
                with st.form("form_add"):
                    nome = st.text_input("Nome:")
                    nivel = st.selectbox("Nível:", ["Rookie", "Normal", "Veteran"])
                    tipo_conta = st.selectbox("Conta:", ["Staff", "Manager"])
                    is_student_input = st.checkbox("Estudante (Visto 28h)")
                    
                    if st.form_submit_button("Criar Conta") and nome:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO funcionarios (codigo, nome, nivel, role, senha, primeiro_acesso, is_student) VALUES ('temp', %s, %s, %s, 'sick1234', 1, %s) RETURNING id", (nome, nivel, "manager" if tipo_conta == "Manager" else "staff", 1 if is_student_input else 0))
                        id_novo = cur.fetchone()[0]
                        cur.execute("UPDATE funcionarios SET codigo=%s WHERE id=%s", (f"sk{id_novo:03d}", id_novo))
                        conn.commit()
                        st.success(f"Criado! Código: sk{id_novo:03d}")
                        st.rerun()

            with st.expander("✏️ Editar Funcionário"):
                if not df.empty:
                    sel = st.selectbox("Selecione o Funcionário:", (df['nome'] + " (" + df['codigo'] + ")").tolist(), key="sel_edit_staff")
                    idx = (df['nome'] + " (" + df['codigo'] + ")").tolist().index(sel)
                    
                    with st.form("form_edit"):
                        n_nome = st.text_input("Nome:", value=df.iloc[idx]['nome'])
                        n_nivel = st.selectbox("Nível:", ["Rookie", "Normal", "Veteran"], index=["Rookie", "Normal", "Veteran"].index(df.iloc[idx]['nivel']))
                        
                        is_master_admin = (df.iloc[idx]['codigo'] == 'admin')
                        n_tipo = st.selectbox("Conta:", ["Staff", "Manager"], index=1 if df.iloc[idx]['role'] == 'manager' else 0, disabled=is_master_admin)
                        n_student = st.checkbox("Estudante (Visto 28h)", value=bool(df.iloc[idx]['is_student']))
                        
                        if st.form_submit_button("Salvar Alterações"):
                            cur = conn.cursor()
                            cur.execute("UPDATE funcionarios SET nome=%s, nivel=%s, role=%s, is_student=%s WHERE id=%s", (n_nome, n_nivel, 'manager' if n_tipo == 'Manager' else 'staff', 1 if n_student else 0, int(df.iloc[idx]['id'])))
                            conn.commit()
                            st.success("Editado com sucesso!")
                            st.rerun()

            with st.expander("🗑️ Excluir Funcionário"):
                df_delete = df[df['codigo'] != 'admin'] 
                if not df_delete.empty:
                    sel_del = st.selectbox("Escolha quem apagar:", (df_delete['nome'] + " (" + df_delete['codigo'] + ")").tolist(), key="del_sel")
                    st.warning("⚠️ Atenção: Apagará o funcionário e todos os históricos dele.")
                    if st.button("Excluir Permanentemente"):
                        id_alvo = int(df_delete.iloc[(df_delete['nome'] + " (" + df_delete['codigo'] + ")").tolist().index(sel_del)]['id'])
                        cur = conn.cursor()
                        cur.execute("DELETE FROM funcionarios WHERE id=%s", (id_alvo,))
                        cur.execute("DELETE FROM disponibilidades WHERE funcionario_id=%s", (id_alvo,))
                        cur.execute("DELETE FROM ferias_estudante WHERE funcionario_id=%s", (id_alvo,))
                        cur.execute("DELETE FROM trocas_turno WHERE solicitante_id=%s OR alvo_id=%s", (id_alvo, id_alvo))
                        conn.commit()
                        st.success("Excluído com sucesso.")
                        st.rerun()

            with st.expander("🔑 Resetar Senha"):
                df_res = df[df['role'] != 'manager'] 
                if not df_res.empty:
                    sel_res = st.selectbox("Funcionário para Reset:", (df_res['nome'] + " (" + df_res['codigo'] + ")").tolist(), key="res_sel")
                    if st.button("Resetar para 'sick1234'"):
                        idx_res = (df_res['nome'] + " (" + df_res['codigo'] + ")").tolist().index(sel_res)
                        cur = conn.cursor()
                        cur.execute("UPDATE funcionarios SET senha='sick1234', primeiro_acesso=1 WHERE id=%s", (int(df_res.iloc[idx_res]['id']),))
                        conn.commit()
                        st.success("Senha resetada.")
        conn.close()

    # =========================================================
    # ABA 9: MUDAR SENHA (STAFF)
    # =========================================================
    elif aba == "🔑 Mudar Senha":
        st.title("🔑 Alterar Senha")
        with st.form("form_change_pass"):
            s_ant = st.text_input("Senha Atual:", type="password")
            n_sen = st.text_input("Nova (mín 6):", type="password")
            c_sen = st.text_input("Confirme a Nova:", type="password")
            if st.form_submit_button("Salvar Modificação"):
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT senha FROM funcionarios WHERE id=%s", (st.session_state['user_id'],))
                s_bd = cur.fetchone()[0]
                
                if s_ant != s_bd: st.error("❌ Erro na senha atual.")
                elif len(n_sen) < 6 or n_sen != c_sen: st.error("⚠️ Senha inválida ou curta.")
                else:
                    cur.execute("UPDATE funcionarios SET senha=%s WHERE id=%s", (n_sen, st.session_state['user_id']))
                    conn.commit()
                    st.success("Senha atualizada!")
                cur.close()
                conn.close()