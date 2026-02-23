import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import os
from datetime import datetime

# --- CONFIGURAÇÕES DE AMBIENTE E INTERFACE ---
os.environ['CURL_CA_BUNDLE'] = ""
os.environ['SSL_CERT_FILE'] = ""
st.set_page_config(page_title="Terminal Léo Pro v14.0", layout="wide", page_icon="📈")


# --- 1. FUNÇÕES DE CONEXÃO GOOGLE SHEETS (NUVEM) ---
def conectar_google():
    """Tenta conectar à API do Google Sheets usando os Secrets do Streamlit"""
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # Verifica se o Secret existe antes de tentar usar
        if "gcp_service_account" not in st.secrets:
            return None

        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Dados_Terminal_Leo")
    except Exception as e:
        st.error(f"Erro na conexão com Google Cloud: {e}")
        return None


def carregar_dados_nuvem(aba_nome):
    """Carrega os dados de uma aba específica da planilha"""
    sh = conectar_google()
    if sh:
        try:
            aba = sh.worksheet(aba_nome)
            data = aba.get_all_records()
            df = pd.DataFrame(data)
            # Converte coluna Valor para número se ela existir
            if not df.empty and 'Valor' in df.columns:
                df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
            return df
        except:
            return pd.DataFrame()
    return pd.DataFrame()


def salvar_dados_nuvem(df, aba_nome):
    """Sobrescreve a aba da planilha com os dados atuais do DataFrame"""
    sh = conectar_google()
    if sh:
        try:
            try:
                aba = sh.worksheet(aba_nome)
            except:
                # Se a aba não existir, cria uma nova
                aba = sh.add_worksheet(title=aba_nome, rows="1000", cols="20")

            aba.clear()
            # Converte tudo para string para garantir compatibilidade com o Google Sheets
            df_string = df.astype(str)
            aba.update([df.columns.values.tolist()] + df_string.values.tolist())
            st.toast(f"✅ Dados de {aba_nome} salvos na Nuvem!")
            return True
        except Exception as e:
            st.error(f"Erro ao salvar na nuvem: {e}")
            return False
    return False


# --- 2. INICIALIZAÇÃO DE DADOS (SESSION STATE) ---
# Inicialização de Finanças
if 'transacoes' not in st.session_state:
    st.session_state.transacoes = pd.DataFrame(
        columns=['ID', 'Data', 'Tipo', 'Categoria', 'Descricao', 'Valor', 'Mes_Ano'])
    # Tenta carregar dados existentes da nuvem
    df_nuvem = carregar_dados_nuvem("Financas")
    if not df_nuvem.empty:
        st.session_state.transacoes = df_nuvem

# Inicialização de Carteira FII
if 'carteira' not in st.session_state:
    df_cart_nuvem = carregar_dados_nuvem("Carteira")
    if not df_cart_nuvem.empty:
        # Reconverte a tabela para o formato de dicionário da carteira
        st.session_state.carteira = df_cart_nuvem.set_index('Ticker').to_dict('index')
    else:
        # Carteira padrão se a planilha estiver vazia
        st.session_state.carteira = {
            "VISC11": {"qtd": 4, "pm": 109.86},
            "PVBI11": {"qtd": 5, "pm": 83.93},
            "BTLG11": {"qtd": 4, "pm": 103.87},
            "CPTS11": {"qtd": 37, "pm": 8.25}
        }


# --- 3. MOTOR DE ANÁLISE TÉCNICA (RADAR) ---
def realizar_analise_pro(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['Mid'] = df['Close'].rolling(window=20).mean()
    std = df['Close'].rolling(window=20).std()
    df['Lower'] = df['Mid'] - (std * 2)
    df['Vol_Med'] = df['Volume'].rolling(window=20).mean()
    return df


@st.cache_data(ttl=600)
def buscar_cotacoes_fii(tickers):
    resumo = []
    for t in tickers:
        try:
            ticker_obj = yf.Ticker(f"{t}.SA")
            hist = ticker_obj.history(period="1d")
            p_atual = float(hist['Close'].iloc[-1]) if not hist.empty else 0.0
            pvp = ticker_obj.info.get('priceToBook', 0.0)
            resumo.append({"Ticker": t, "Preço": p_atual, "P/VP": pvp})
        except:
            continue
    return pd.DataFrame(resumo)


# --- 4. INTERFACE ---
tab_fii, tab_reg_fii, tab_trade, tab_financas = st.tabs([
    "🏙️ Carteira FII", "➕ Compras FII", "🎯 Radar Trade PRO", "💰 Gestão Financeira"
])

# ABA 1: CARTEIRA FII
with tab_fii:
    st.title("🏙️ Dashboard de Ativos")
    df_precos = buscar_cotacoes_fii(list(st.session_state.carteira.keys()))
    if not df_precos.empty:
        df_base = pd.DataFrame.from_dict(st.session_state.carteira, orient='index').reset_index().rename(
            columns={'index': 'Ticker'})
        df_resumo = pd.merge(df_base, df_precos, on='Ticker')
        df_resumo['Investido'] = df_resumo['qtd'] * df_resumo['pm']
        df_resumo['Patrimônio'] = df_resumo['qtd'] * df_resumo['Preço']
        df_resumo['Lucro'] = df_resumo['Patrimônio'] - df_resumo['Investido']

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Investido", f"R$ {df_resumo['Investido'].sum():.2f}")
        col2.metric("Patrimônio Atual", f"R$ {df_resumo['Patrimônio'].sum():.2f}")
        col3.metric("Lucro/Prejuízo", f"R$ {df_resumo['Lucro'].sum():.2f}",
                    f"{(df_resumo['Lucro'].sum() / df_resumo['Investido'].sum()) * 100:.2f}%")

        st.plotly_chart(px.pie(df_resumo, values='Patrimônio', names='Ticker', hole=0.5, title="Divisão da Carteira"),
                        use_container_width=True)
        st.dataframe(df_resumo.style.format({'pm': '{:.2f}', 'Preço': '{:.2f}', 'Lucro': '{:.2f}'}),
                     use_container_width=True)

# ABA 2: REGISTRAR COMPRAS
with tab_reg_fii:
    st.subheader("➕ Registrar Nova Compra")
    with st.form("form_compra"):
        t_compra = st.selectbox("Ticker", list(st.session_state.carteira.keys()))
        q_compra = st.number_input("Quantidade", min_value=1, step=1)
        p_compra = st.number_input("Preço Pago", min_value=0.01)
        if st.form_submit_button("Atualizar e Salvar na Nuvem"):
            qtd_ant = st.session_state.carteira[t_compra]['qtd']
            pm_ant = st.session_state.carteira[t_compra]['pm']
            # Novo PM
            st.session_state.carteira[t_compra]['pm'] = ((qtd_ant * pm_ant) + (q_compra * p_compra)) / (
                        qtd_ant + q_compra)
            st.session_state.carteira[t_compra]['qtd'] += q_compra

            # Salvar no Google Sheets
            df_cart_save = pd.DataFrame.from_dict(st.session_state.carteira, orient='index').reset_index().rename(
                columns={'index': 'Ticker'})
            salvar_dados_nuvem(df_cart_save, "Carteira")
            st.success("Carteira atualizada!")
            st.rerun()

# ABA 3: RADAR TRADE
with tab_trade:
    st.subheader("🎯 Análise Técnica PRO")
    ativos = {"Bitcoin": "BTC-USD", "Dólar": "USDBRL=X", "Vale": "VALE3.SA", "Petrobras": "PETR4.SA"}
    escolha = st.selectbox("Ativo", list(ativos.keys()))
    df_t = yf.download(ativos[escolha], period="100d", progress=False)
    if not df_t.empty:
        if isinstance(df_t.columns, pd.MultiIndex): df_t.columns = df_t.columns.get_level_values(0)
        df_t = realizar_analise_pro(df_t)

        # Lógica de confluência
        p, r, e9, e21, m, s, lb = df_t['Close'].iloc[-1], df_t['RSI'].iloc[-1], df_t['EMA9'].iloc[-1], \
        df_t['EMA21'].iloc[-1], df_t['MACD'].iloc[-1], df_t['Signal'].iloc[-1], df_t['Lower'].iloc[-1]
        pontos = sum([r < 45, e9 > e21, m > s, p < (lb * 1.05)])

        status, cor = ("🚀 COMPRA", "#27ae60") if pontos >= 3 else ("⚖️ AGUARDAR", "#95a5a6")
        st.markdown(
            f"<div style='background-color:{cor};padding:15px;border-radius:10px;text-align:center;color:white;'><h2>{status} ({pontos}/4)</h2></div>",
            unsafe_allow_html=True)

        fig = go.Figure(data=[
            go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'])])
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)

# ABA 4: GESTÃO FINANCEIRA
with tab_financas:
    st.title("💰 Gestão Organizze Cloud")
    with st.expander("➕ Adicionar Lançamento"):
        with st.form("form_fin"):
            c1, c2 = st.columns(2)
            f_dat = c1.date_input("Data", datetime.now())
            f_tip = c2.selectbox("Tipo", ["Receita", "Despesa"])
            f_cat = st.text_input("Categoria")
            f_des = st.text_input("Descrição")
            f_val = st.number_input("Valor", min_value=0.01)

            if st.form_submit_button("Confirmar Lançamento"):
                nova = pd.DataFrame([[str(datetime.now().timestamp()), str(f_dat), f_tip, f_cat, f_des, f_val,
                                      f_dat.strftime("%Y-%m")]],
                                    columns=['ID', 'Data', 'Tipo', 'Categoria', 'Descricao', 'Valor', 'Mes_Ano'])
                st.session_state.transacoes = pd.concat([st.session_state.transacoes, nova], ignore_index=True)
                salvar_dados_nuvem(st.session_state.transacoes, "Financas")
                st.success("Lançamento salvo com sucesso!")
                st.rerun()

    if not st.session_state.transacoes.empty:
        df_fin = st.session_state.transacoes.copy()
        meses = sorted(df_fin['Mes_Ano'].unique(), reverse=True)

        for m in meses:
            st.subheader(f"📅 Mês: {m}")
            df_m = df_fin[df_fin['Mes_Ano'] == m]

            col1, col2 = st.columns([1, 2])
            with col1:
                # Gráfico de pizza de gastos
                df_gastos = df_m[df_m['Tipo'] == 'Despesa']
                if not df_gastos.empty:
                    st.plotly_chart(px.pie(df_gastos, values='Valor', names='Categoria', hole=0.3),
                                    use_container_width=True)
            with col2:
                # Tabela e botão excluir
                st.table(df_m[['Data', 'Categoria', 'Descricao', 'Valor']])
                for i, row in df_m.iterrows():
                    if st.button(f"🗑️ Excluir {row['Categoria']} (R$ {row['Valor']})", key=row['ID']):
                        st.session_state.transacoes = st.session_state.transacoes[
                            st.session_state.transacoes['ID'] != row['ID']]
                        salvar_dados_nuvem(st.session_state.transacoes, "Financas")
                        st.rerun()
