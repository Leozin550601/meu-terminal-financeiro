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

st.set_page_config(page_title="Terminal Léo Pro v4.0", layout="wide", page_icon="📈")

# --- 1. INICIALIZAÇÃO DA CARTEIRA FII ---
if 'carteira' not in st.session_state:
    st.session_state.carteira = {
        "VISC11": {"qtd": 4, "pm": 109.86},
        "PVBI11": {"qtd": 5, "pm": 83.93},
        "BTLG11": {"qtd": 4, "pm": 103.87},
        "CPTS11": {"qtd": 37, "pm": 8.25}
    }


# --- 2. MOTOR DE ANÁLISE TÉCNICA (TRADE) ---
def realizar_analise_pro(df):
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    # Médias Exponenciais
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    # MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    # Bollinger e Volume
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
                # REGRA SOLICITADA: Zerar dividendos se for Fevereiro
                div_cota = 0.0 if hoje.month == 2 else float(
                    obj.actions['Dividends'].iloc[-1] if not obj.actions.empty else 0.0)
                lista.append({"Ticker": t, "Preço Atual": p_at, "P/VP": pvp, "Div_Cota": div_cota})
        except:
            continue
    return pd.DataFrame(lista)


# --- 3. INTERFACE EM ABAS ---
tab_fii, tab_reg, tab_trade = st.tabs(["🏙️ Carteira de FIIs", "➕ Registrar Compra", "🎯 Radar de Confluência PRO"])

# --- ABA 1: DASHBOARD FII ---
with tab_fii:
    st.title("🏙️ Gestão de Ativos Imobiliários")
    df_m = buscar_dados_fii(list(st.session_state.carteira.keys()))

    if not df_m.empty:
        df_u = pd.DataFrame.from_dict(st.session_state.carteira, orient='index').reset_index().rename(
            columns={'index': 'Ticker'})
        df = pd.merge(df_u, df_m, on='Ticker')
        df['Investido'] = df['qtd'] * df['pm']
        df['Atual'] = df['qtd'] * df['Preço Atual']
        df['Renda_Fev'] = df['qtd'] * df['Div_Cota']
        df['Lucro_RS'] = df['Atual'] - df['Investido']

        # Métricas
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Investido", f"R$ {df['Investido'].sum():.2f}")
        m2.metric("Patrimônio Atual", f"R$ {df['Atual'].sum():.2f}")
        m3.metric("Renda Fevereiro", f"R$ {df['Renda_Fev'].sum():.2f}", delta="Ajuste de Repasse")
        m4.metric("Lucro Total", f"R$ {df['Lucro_RS'].sum():.2f}",
                  f"{(df['Lucro_RS'].sum() / df['Investido'].sum()) * 100:.2f}%")

        # Gráficos de FII
        st.markdown("---")
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.pie(df, values='Atual', names='Ticker', title="Peso na Carteira (%)", hole=0.5),
                            use_container_width=True)
        with g2:
            st.plotly_chart(
                px.bar(df, x='Ticker', y=['pm', 'Preço Atual'], barmode='group', title="Preço Médio vs Mercado"),
                use_container_width=True)

        st.dataframe(df.style.format(
            {'pm': '{:.2f}', 'Preço Atual': '{:.2f}', 'P/VP': '{:.2f}', 'Renda_Fev': '{:.2f}', 'Lucro_RS': '{:.2f}'}),
                     use_container_width=True)

# --- ABA 2: REGISTRO ---
with tab_reg:
    st.subheader("➕ Atualizar Minhas Cotas")
    with st.form("add_fii"):
        c_sel = st.selectbox("Selecione o Fundo", list(st.session_state.carteira.keys()))
        q_new = st.number_input("Quantidade Comprada", min_value=1)
        p_new = st.number_input("Preço da Unidade (R$)", min_value=0.01)
        if st.form_submit_button("Salvar na Carteira"):
            st.session_state.carteira[c_sel]['pm'] = ((st.session_state.carteira[c_sel]['qtd'] *
                                                       st.session_state.carteira[c_sel]['pm']) + (q_new * p_new)) / (
                                                                 st.session_state.carteira[c_sel]['qtd'] + q_new)
            st.session_state.carteira[c_sel]['qtd'] += q_new
            st.success(f"Cotas de {c_sel} atualizadas com sucesso!")
            st.rerun()

# --- ABA 3: RADAR DE TRADE PRO ---
with tab_trade:
    st.subheader("🎯 Radar de Alta Precisão (Confluência de Indicadores)")
    ativos = {
        "Dólar": "USDBRL=X", "Bitcoin": "BTC-USD", "Solana": "SOL-USD",
        "Ethereum": "ETH-USD", "Vale": "VALE3.SA", "Petrobras": "PETR4.SA"
    }
    sel = st.selectbox("Escolha o Ativo:", list(ativos.keys()))
    df_t = yf.download(ativos[sel], period="100d", interval="1d", progress=False)

    if not df_t.empty:
        if isinstance(df_t.columns, pd.MultiIndex): df_t.columns = df_t.columns.get_level_values(0)
        df_t = realizar_analise_pro(df_t)

        # Variáveis de Decisão
        p_at = float(df_t['Close'].iloc[-1]);
        rsi = float(df_t['RSI'].iloc[-1])
        ema9 = float(df_t['EMA9'].iloc[-1]);
        ema21 = float(df_t['EMA21'].iloc[-1])
        macd = float(df_t['MACD'].iloc[-1]);
        sig = float(df_t['Signal'].iloc[-1])
        vol = float(df_t['Volume'].iloc[-1]);
        v_med = float(df_t['Vol_Med'].iloc[-1])
        low_b = float(df_t['Lower'].iloc[-1]);
        up_b = float(df_t['Upper'].iloc[-1])

        # SCORE DE SEGURANÇA (Confluência)
        pontos = 0
        mensagens = []
        if rsi < 40: pontos += 1; mensagens.append("✅ RSI: Preço Descontado")
        if ema9 > ema21: pontos += 1; mensagens.append("✅ Média: Tendência de Alta")
        if macd > sig: pontos += 1; mensagens.append("✅ MACD: Momento de Compra")
        if vol > v_med: pontos += 1; mensagens.append("✅ Volume: Fluxo Confirmado")
        if p_at < (low_b * 1.05): pontos += 1; mensagens.append("✅ Bollinger: No Suporte")

        if pontos >= 4:
            res, cor = "🚀 ALINHAMENTO TOTAL: COMPRA SEGURA", "#27ae60"
        elif pontos == 3:
            res, cor = "⚖️ ALINHAMENTO PARCIAL: SEGURAR", "#f1c40f"
        elif rsi > 70 or p_at > up_b:
            res, cor = "⚠️ ALERTA: SOBRECOMPRA (VENDER)", "#e74c3c"
        else:
            res, cor = "❌ SEM CONFLUÊNCIA: AGUARDAR", "#95a5a6"

        st.markdown(
            f"<div style='background-color:{cor};padding:20px;border-radius:10px;text-align:center'><h2 style='color:white;margin:0'>{res}</h2></div>",
            unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Preço Atual", f"{p_at:.2f}")
        c2.metric("Força RSI", f"{rsi:.1f}")
        c3.metric("Volume vs Média", "🔥 ALTO" if vol > v_med else "❄️ BAIXO")

        # Gráfico Candlestick
        fig = go.Figure(data=[
            go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'],
                           name='Preço')])
        fig.add_trace(go.Scatter(x=df_t.index, y=df_t['EMA9'], name='EMA 9', line=dict(color='yellow')))
        fig.add_trace(go.Scatter(x=df_t.index, y=df_t['EMA21'], name='EMA 21', line=dict(color='magenta')))
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500,
                          margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

        st.write("### ✅ Checklist de Confluência:")
        st.info(" | ".join(mensagens) if mensagens else "Nenhum sinal técnico de compra detectado.")