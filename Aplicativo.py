import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime

# --- CONFIGURAÇÕES DE AMBIENTE ---
os.environ['CURL_CA_BUNDLE'] = ""
os.environ['SSL_CERT_FILE'] = ""
st.set_page_config(page_title="Terminal Léo Pro v12.0", layout="wide", page_icon="📈")

# --- 1. INICIALIZAÇÃO DE DADOS (SESSION STATE) ---
if 'carteira' not in st.session_state:
    st.session_state.carteira = {
        "VISC11": {"qtd": 4, "pm": 109.86},
        "PVBI11": {"qtd": 5, "pm": 83.93},
        "BTLG11": {"qtd": 4, "pm": 103.87},
        "CPTS11": {"qtd": 37, "pm": 8.25}
    }

if 'transacoes' not in st.session_state:
    st.session_state.transacoes = pd.DataFrame(
        columns=['ID', 'Data', 'Tipo', 'Categoria', 'Descricao', 'Valor', 'Mes_Ano'])


# --- 2. MOTORES DE ANÁLISE (TRADE & FII) ---
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


# --- 3. INTERFACE EM ABAS ---
tab_fii, tab_reg_fii, tab_trade, tab_financas = st.tabs([
    "🏙️ Carteira FII",
    "➕ Registrar Compra FII",
    "🎯 Radar Trade PRO",
    "💰 Gestão Financeira"
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
    with st.form("form_reg_fii"):
        t_sel = st.selectbox("Ticker", list(st.session_state.carteira.keys()))
        q_com = st.number_input("Qtd Comprada", min_value=1)
        p_pag = st.number_input("Preço Pago (R$)", min_value=0.01)
        if st.form_submit_button("Atualizar Carteira"):
            qtd_ant = st.session_state.carteira[t_sel]['qtd']
            pm_ant = st.session_state.carteira[t_sel]['pm']
            st.session_state.carteira[t_sel]['pm'] = ((qtd_ant * pm_ant) + (q_com * p_pag)) / (qtd_ant + q_com)
            st.session_state.carteira[t_sel]['qtd'] += q_com
            st.success(f"Cotas de {t_sel} atualizadas!")
            st.rerun()

# --- ABA 3: RADAR TRADE PRO ---
with tab_trade:
    st.subheader("🎯 Radar de Alta Precisão")
    atv = {"Bitcoin": "BTC-USD", "Dólar": "USDBRL=X", "Vale": "VALE3.SA", "Petrobras": "PETR4.SA"}
    sel = st.selectbox("Escolha o Ativo:", list(atv.keys()))
    df_t = yf.download(atv[sel], period="100d", progress=False)

    if not df_t.empty:
        if isinstance(df_t.columns, pd.MultiIndex): df_t.columns = df_t.columns.get_level_values(0)
        df_t = realizar_analise_pro(df_t)
        p, r, e9, e21, m, s, v, vm, lb = df_t['Close'].iloc[-1], df_t['RSI'].iloc[-1], df_t['EMA9'].iloc[-1], \
        df_t['EMA21'].iloc[-1], df_t['MACD'].iloc[-1], df_t['Signal'].iloc[-1], df_t['Volume'].iloc[-1], \
        df_t['Vol_Med'].iloc[-1], df_t['Lower'].iloc[-1]

        pontos = sum([r < 45, e9 > e21, m > s, v > vm, p < (lb * 1.05)])
        res, cor = ("🚀 COMPRA SEGURA", "#27ae60") if pontos >= 4 else ("⚖️ AGUARDAR", "#95a5a6")
        st.markdown(
            f"<div style='background-color:{cor};padding:15px;border-radius:10px;text-align:center;color:white;'><h2>{res} ({pontos}/5)</h2></div>",
            unsafe_allow_html=True)

        fig = go.Figure(data=[
            go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'],
                           name="Preço")])
        fig.add_trace(go.Scatter(x=df_t.index, y=df_t['EMA9'], name="EMA 9", line=dict(color='yellow')))
        fig.add_trace(go.Scatter(x=df_t.index, y=df_t['EMA21'], name="EMA 21", line=dict(color='magenta')))
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)
        st.info(f"RSI: {r:.1f} | MACD: {m:.2f} | Volume Ratio: {(v / vm if vm > 0 else 0):.1f}x")

# --- ABA 4: GESTÃO FINANCEIRA (SISTEMA ORGANIZZE COMPLETO) ---
with tab_financas:
    st.title("💰 Gestão Financeira Organizze")

    # 1. Formulário para Adicionar Registros
    with st.expander("➕ Adicionar Novo Lançamento (Receita ou Despesa)"):
        with st.form("novo_lancamento_financeiro"):
            c1, c2 = st.columns(2)
            f_data = c1.date_input("Data do Registro", datetime.now())
            f_tipo = c2.selectbox("Tipo de Movimentação", ["Receita", "Despesa"])

            # OPÇÃO DE DIGITAR A CATEGORIA (LIVRE)
            f_categoria = st.text_input("Categoria (Ex: Dividendos, Aluguel, Supermercado, Lazer)")

            f_descricao = st.text_input("Descrição / Histórico")
            f_valor = st.number_input("Valor (R$)", min_value=0.01, step=0.01)

            if st.form_submit_button("Confirmar Lançamento"):
                if f_categoria:
                    mes_referencia = f_data.strftime("%Y-%m")
                    id_transacao = str(datetime.now().timestamp())
                    nova_transacao = pd.DataFrame(
                        [[id_transacao, f_data, f_tipo, f_categoria, f_descricao, f_valor, mes_referencia]],
                        columns=['ID', 'Data', 'Tipo', 'Categoria', 'Descricao', 'Valor', 'Mes_Ano'])
                    st.session_state.transacoes = pd.concat([st.session_state.transacoes, nova_transacao],
                                                            ignore_index=True)
                    st.success("Lançamento registrado com sucesso!")
                    st.rerun()
                else:
                    st.error("Por favor, preencha a categoria.")

    # 2. Exibição por Meses e Gráfico de Pizza
    if not st.session_state.transacoes.empty:
        st.markdown("---")
        lista_meses = sorted(st.session_state.transacoes['Mes_Ano'].unique(), reverse=True)
        abas_mensais = st.tabs([datetime.strptime(m, "%Y-%m").strftime("%m/%Y") for m in lista_meses])

        for idx, m_ref in enumerate(lista_meses):
            with abas_mensais[idx]:
                df_mes = st.session_state.transacoes[st.session_state.transacoes['Mes_Ano'] == m_ref]
                receitas_total = df_mes[df_mes['Tipo'] == 'Receita']['Valor'].sum()
                despesas_total = df_mes[df_mes['Tipo'] == 'Despesa']['Valor'].sum()

                # Métricas do Mês
                met1, met2, met3 = st.columns(3)
                met1.metric("Receitas", f"R$ {receitas_total:.2f}")
                met2.metric("Despesas", f"R$ {despesas_total:.2f}", delta_color="inverse")
                met3.metric("Saldo Líquido", f"R$ {receitas_total - despesas_total:.2f}")

                # GRÁFICO EM PIZZA (DISTRIBUIÇÃO DE DESPESAS POR CATEGORIA)
                if not df_mes[df_mes['Tipo'] == 'Despesa'].empty:
                    st.subheader("📊 Distribuição de Gastos")
                    fig_pizza_fin = px.pie(
                        df_mes[df_mes['Tipo'] == 'Despesa'],
                        values='Valor',
                        names='Categoria',
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    st.plotly_chart(fig_pizza_fin, use_container_width=True)

                # HISTÓRICO DE REGISTROS COMPLETO
                st.subheader("📋 Histórico Detalhado")
                # Formatando a tabela para exibição completa das especificações
                df_exibir = df_mes[['Data', 'Tipo', 'Categoria', 'Descricao', 'Valor']].sort_values("Data",
                                                                                                    ascending=False)
                st.table(df_exibir.style.format({'Valor': 'R$ {:.2f}'}))

                # OPÇÃO DE EXCLUIR REGISTROS
                st.markdown("---")
                st.write("🔧 **Gerenciar Registros:**")
                for i_row, row in df_mes.iterrows():
                    if st.button(f"🗑️ Excluir: {row['Categoria']} - {row['Descricao']} (R$ {row['Valor']:.2f})",
                                 key=row['ID']):
                        st.session_state.transacoes = st.session_state.transacoes[
                            st.session_state.transacoes['ID'] != row['ID']]
                        st.rerun()
    else:
        st.info("Nenhum lançamento financeiro registrado até o momento.")

