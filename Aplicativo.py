import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import os
from datetime import datetime

# --- CONFIGURAÇÕES DE AMBIENTE ---
os.environ['CURL_CA_BUNDLE'] = ""
os.environ['SSL_CERT_FILE'] = ""
st.set_page_config(page_title="Terminal Léo Pro v13.0", layout="wide", page_icon="📈")


# --- 1. FUNÇÕES DE CONEXÃO GOOGLE SHEETS (NUVEM) ---
def conectar_google():
    """Estabelece conexão com a planilha do Google usando os Secrets do Streamlit"""
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # Puxa as credenciais configuradas no painel do Streamlit Cloud ou secrets.toml local
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Dados_Terminal_Leo")
    except Exception as e:
        # Silencia o erro para evitar travar o app no modo offline
        return None


def carregar_dados_nuvem(aba_nome):
    """Lê os dados da planilha e converte para DataFrame"""
    sh = conectar_google()
    if sh:
        try:
            aba = sh.worksheet(aba_nome)
            data = aba.get_all_records()
            df = pd.DataFrame(data)
            if not df.empty and 'Valor' in df.columns:
                df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
            return df
        except:
            return pd.DataFrame()
    return pd.DataFrame()


def salvar_dados_nuvem(df, aba_nome):
    """Limpa a aba atual e salva o DataFrame atualizado na nuvem"""
    sh = conectar_google()
    if sh:
        try:
            try:
                aba = sh.worksheet(aba_nome)
            except:
                aba = sh.add_worksheet(title=aba_nome, rows="1000", cols="20")

            aba.clear()
            # Garante que todos os dados sejam convertidos para string para o upload
            df_enviar = df.astype(str)
            aba.update([df.columns.values.tolist()] + df_enviar.values.tolist())
        except Exception as e:
            st.error(f"Erro ao salvar na nuvem: {e}")


# --- 2. INICIALIZAÇÃO DE DADOS (SESSION STATE + TRAVA OFF-LINE) ---
if 'transacoes' not in st.session_state:
    # Inicializamos como DataFrame vazio primeiro para evitar NameError
    st.session_state.transacoes = pd.DataFrame(
        columns=['ID', 'Data', 'Tipo', 'Categoria', 'Descricao', 'Valor', 'Mes_Ano'])

    try:
        # Tentativa de buscar dados reais da planilha
        df_buscado = carregar_dados_nuvem("Financas")
        if not df_buscado.empty:
            st.session_state.transacoes = df_buscado
    except Exception:
        # Se falhar (falta de secrets ou net), o app continua vazio mas funcional
        st.warning("Rodando em modo offline (Segredos não configurados).")

if 'carteira' not in st.session_state:
    # Tentativa de carregar carteira da nuvem
    try:
        df_cart_cloud = carregar_dados_nuvem("Carteira")
        if not df_cart_cloud.empty:
            st.session_state.carteira = df_cart_cloud.set_index('Ticker').to_dict('index')
        else:
            raise Exception("Vazio")
    except:
        # Se falhar, usa a carteira padrão do sistema
        st.session_state.carteira = {
            "VISC11": {"qtd": 4, "pm": 109.86},
            "PVBI11": {"qtd": 5, "pm": 83.93},
            "BTLG11": {"qtd": 4, "pm": 103.87},
            "CPTS11": {"qtd": 37, "pm": 8.25}
        }


# --- 3. MOTOR TÉCNICO ---
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
    df['Upper'] = df['Mid'] + (std * 2)
    df['Lower'] = df['Mid'] - (std * 2)
    df['Vol_Med'] = df['Volume'].rolling(window=20).mean()
    return df


@st.cache_data(ttl=600)
def buscar_dados_fii(tickers):
    lista = []
    hoje = datetime.now()
    for t in tickers:
        try:
            obj = yf.Ticker(f"{t}.SA")
            hist = obj.history(period="1mo")
            if not hist.empty:
                p_at = float(hist['Close'].iloc[-1])
                pvp = obj.info.get('priceToBook', 0.0)
                div = 0.0 if hoje.month == 2 else float(
                    obj.actions['Dividends'].iloc[-1] if not obj.actions.empty else 0.0)
                lista.append({"Ticker": t, "Preço": p_at, "P/VP": pvp, "Div": div})
        except:
            continue
    return pd.DataFrame(lista)


# --- 4. INTERFACE EM ABAS ---
tab_fii, tab_reg_fii, tab_trade, tab_financas = st.tabs([
    "🏙️ Carteira FII", "➕ Registrar Compra FII", "🎯 Radar Trade PRO", "💰 Gestão Financeira"
])

# --- ABA 1: DASHBOARD FII ---
with tab_fii:
    st.title("🏙️ Dashboard de Ativos")
    df_m = buscar_dados_fii(list(st.session_state.carteira.keys()))
    if not df_m.empty:
        df_u = pd.DataFrame.from_dict(st.session_state.carteira, orient='index').reset_index().rename(
            columns={'index': 'Ticker'})
        df = pd.merge(df_u, df_m, on='Ticker')
        df['Investido'] = df['qtd'] * df['pm']
        df['Atual'] = df['qtd'] * df['Preço']
        df['Lucro_RS'] = df['Atual'] - df['Investido']

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Investido", f"R$ {df['Investido'].sum():.2f}")
        m2.metric("Patrimônio", f"R$ {df['Atual'].sum():.2f}")
        m3.metric("Lucro Bruto", f"R$ {df['Lucro_RS'].sum():.2f}",
                  f"{(df['Lucro_RS'].sum() / df['Investido'].sum()) * 100:.2f}%")

        c_g1, c_g2 = st.columns(2)
        with c_g1: st.plotly_chart(px.pie(df, values='Atual', names='Ticker', title="Peso na Carteira", hole=0.5),
                                   use_container_width=True)
        with c_g2: st.plotly_chart(px.bar(df, x='Ticker', y=['pm', 'Preço'], barmode='group', title="PM vs Mercado"),
                                   use_container_width=True)
        st.dataframe(df.style.format({'pm': '{:.2f}', 'Preço': '{:.2f}', 'P/VP': '{:.2f}', 'Lucro_RS': '{:.2f}'}),
                     use_container_width=True)

# --- ABA 2: REGISTRAR COMPRA FII ---
with tab_reg_fii:
    st.subheader("➕ Adicionar Novas Cotas")
    with st.form("form_registro_fii"):
        ticker_sel = st.selectbox("Selecione o Fundo", list(st.session_state.carteira.keys()))
        qtd_comprada = st.number_input("Quantidade Comprada", min_value=1, step=1)
        preco_pago = st.number_input("Preço por Cota (R$)", min_value=0.01, format="%.2f")

        if st.form_submit_button("Confirmar Compra"):
            qtd_antiga = st.session_state.carteira[ticker_sel]['qtd']
            pm_antigo = st.session_state.carteira[ticker_sel]['pm']
            nova_qtd = qtd_antiga + qtd_comprada
            novo_pm = ((qtd_antiga * pm_antigo) + (qtd_comprada * preco_pago)) / nova_qtd
            st.session_state.carteira[ticker_sel]['qtd'] = nova_qtd
            st.session_state.carteira[ticker_sel]['pm'] = novo_pm
            # Salvar Carteira na Nuvem
            df_para_salvar = pd.DataFrame.from_dict(st.session_state.carteira, orient='index').reset_index().rename(
                columns={'index': 'Ticker'})
            salvar_dados_nuvem(df_para_salvar, "Carteira")
            st.success(f"Cotas de {ticker_sel} atualizadas!")
            st.rerun()

# --- ABA 3: RADAR TRADE PRO ---
with tab_trade:
    st.subheader("🎯 Radar de Alta Precisão")
    ativos_radar = {"Bitcoin": "BTC-USD", "Dólar": "USDBRL=X", "Vale": "VALE3.SA", "Petrobras": "PETR4.SA"}
    sel_ativo = st.selectbox("Escolha o Ativo:", list(ativos_radar.keys()))
    df_trade = yf.download(ativos_radar[sel_ativo], period="100d", progress=False)
    if not df_trade.empty:
        if isinstance(df_trade.columns, pd.MultiIndex): df_trade.columns = df_trade.columns.get_level_values(0)
        df_trade = realizar_analise_pro(df_trade)
        p, r, e9, e21, m, s, v, vm, lb = df_trade['Close'].iloc[-1], df_trade['RSI'].iloc[-1], df_trade['EMA9'].iloc[
            -1], df_trade['EMA21'].iloc[-1], df_trade['MACD'].iloc[-1], df_trade['Signal'].iloc[-1], \
        df_trade['Volume'].iloc[-1], df_trade['Vol_Med'].iloc[-1], df_trade['Lower'].iloc[-1]
        pontos = sum([r < 45, e9 > e21, m > s, v > vm, p < (lb * 1.05)])
        res, cor = ("🚀 COMPRA SEGURA", "#27ae60") if pontos >= 4 else ("⚖️ AGUARDAR", "#95a5a6")
        st.markdown(
            f"<div style='background-color:{cor};padding:15px;border-radius:10px;text-align:center;color:white;'><h2>{res} ({pontos}/5)</h2></div>",
            unsafe_allow_html=True)
        fig_trade = go.Figure(data=[
            go.Candlestick(x=df_trade.index, open=df_trade['Open'], high=df_trade['High'], low=df_trade['Low'],
                           close=df_trade['Close'], name="Preço")])
        fig_trade.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=450)
        st.plotly_chart(fig_trade, use_container_width=True)

# --- ABA 4: GESTÃO FINANCEIRA ---
with tab_financas:
    st.title("💰 Gestão Financeira Organizze")
    with st.expander("➕ Novo Lançamento"):
        with st.form("form_fin_nuvem"):
            c1, c2 = st.columns(2)
            f_data = c1.date_input("Data", datetime.now())
            f_tipo = c2.selectbox("Tipo", ["Receita", "Despesa"])
            f_cat = st.text_input("Categoria")
            f_desc = st.text_input("Descrição")
            f_val = st.number_input("Valor (R$)", min_value=0.01)

            if st.form_submit_button("Confirmar e Salvar"):
                mes_a = f_data.strftime("%Y-%m")
                id_t = str(datetime.now().timestamp())
                nova_linha = pd.DataFrame([[id_t, str(f_data), f_tipo, f_cat, f_desc, f_val, mes_a]],
                                          columns=['ID', 'Data', 'Tipo', 'Categoria', 'Descricao', 'Valor', 'Mes_Ano'])
                st.session_state.transacoes = pd.concat([st.session_state.transacoes, nova_linha], ignore_index=True)
                salvar_dados_nuvem(st.session_state.transacoes, "Financas")
                st.success("Salvo na Nuvem!")
                st.rerun()

    if not st.session_state.transacoes.empty:
        lista_m = sorted(st.session_state.transacoes['Mes_Ano'].unique(), reverse=True)
        abas_meses = st.tabs([str(m) for m in lista_m])
        for i, m_ref in enumerate(lista_m):
            with abas_meses[i]:
                df_mes = st.session_state.transacoes[st.session_state.transacoes['Mes_Ano'] == m_ref]
                # Gráfico
                if not df_mes[df_mes['Tipo'] == 'Despesa'].empty:
                    st.plotly_chart(
                        px.pie(df_mes[df_mes['Tipo'] == 'Despesa'], values='Valor', names='Categoria', hole=0.4),
                        use_container_width=True)
                # Tabela e Exclusão
                st.table(df_mes[['Data', 'Tipo', 'Categoria', 'Descricao', 'Valor']])
                for idx_row, row in df_mes.iterrows():
                    if st.button(f"🗑️ Apagar {row['Categoria']} (R$ {row['Valor']})", key=row['ID']):
                        st.session_state.transacoes = st.session_state.transacoes[
                            st.session_state.transacoes['ID'] != row['ID']]
                        salvar_dados_nuvem(st.session_state.transacoes, "Financas")
                        st.rerun()
