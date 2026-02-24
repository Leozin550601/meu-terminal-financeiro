import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import io
from datetime import datetime

# --- CONFIGURAÇÃO TELEGRAM (SUA CONTA) ---
TOKEN_TELEGRAM = "8743991870:AAHTyCif9quO69YxMuCV5eeRI_lXuvOtJ30"
CHAT_ID = "1104806225"

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sniper Ultimate v38.0", layout="wide", page_icon="🎯")


# --- FUNÇÕES DE SUPORTE ---
def enviar_alerta_completo(mensagem, fig=None):
    """Envia texto e imagem do gráfico para o Telegram"""
    try:
        url_text = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage?chat_id={CHAT_ID}&text={mensagem}"
        requests.get(url_text)
        if fig:
            img_bytes = fig.to_image(format="png", width=1000, height=600)
            url_photo = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendPhoto"
            requests.post(url_photo, files={'photo': ('grafico.png', img_bytes)}, data={'chat_id': CHAT_ID})
    except Exception as e:
        st.error(f"Erro ao disparar Telegram: {e}")


def calcular_indicadores(df):
    """Calcula a biblioteca técnica do Sniper"""
    if df.empty: return df
    # RSI (Força Relativa)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    # Médias Móveis (5, 13 e a Mestra 200)
    df['EMA_FAST'] = df['Close'].ewm(span=5, adjust=False).mean()
    df['EMA_SLOW'] = df['Close'].ewm(span=13, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    # MACD
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['Signal_MACD'] = df['MACD'].ewm(span=9, adjust=False).mean()
    # Volume e Volatilidade (ATR)
    df['Vol_Med'] = df['Volume'].rolling(window=20).mean()
    df['ATR'] = (df['High'] - df['Low']).rolling(window=14).mean()
    return df


def executar_backtest(df):
    """Analisa a assertividade dos sinais passados"""
    vitorias, derrotas, lucro = 0, 0, 0
    sinais = df[df['Sinal_Compra'] == True]
    for idx in sinais.index:
        pos = df.index.get_loc(idx)
        if pos + 8 < len(df):
            p_entrada = df.loc[idx, 'Close']
            futuro = df.iloc[pos + 1: pos + 8]
            if futuro['High'].max() > p_entrada * 1.015:  # Alvo 1.5%
                vitorias += 1;
                lucro += 1.5
            elif futuro['Low'].min() < p_entrada * 0.992:  # Stop 0.8%
                derrotas += 1;
                lucro -= 0.8
    total = vitorias + derrotas
    wr = (vitorias / total * 100) if total > 0 else 0
    return wr, lucro


# --- 1. SIDEBAR (SCANNER E CONFIGURAÇÕES) ---
with st.sidebar:
    st.title("🎯 Sniper Command")
    lista_ativos = ["BTC-USD", "ETH-USD", "SOL-USD", "PETR4.SA", "VALE3.SA", "USDBRL=X"]

    st.subheader("🔍 Scanner Multi-Ativos")
    for tic in lista_ativos:
        d_s = yf.download(tic, period="2d", interval="15m", progress=False)
        if not d_s.empty:
            if isinstance(d_s.columns, pd.MultiIndex): d_s.columns = d_s.columns.get_level_values(0)
            d_s = calcular_indicadores(d_s)
            l = d_s.iloc[-1]
            sc = sum(
                [l['RSI'] < 60, l['EMA_FAST'] > l['EMA_SLOW'], l['MACD'] > l['Signal_MACD'], l['Volume'] > l['Vol_Med'],
                 l['Close'] > l['EMA_200']])
            st.caption(f"{tic}: {'🔥 COMPRA' if sc == 5 else '⚪ Aguarde'} ({sc}/5)")

    st.markdown("---")
    ativo_p = st.selectbox("Ativo Principal:", lista_ativos)
    tf_op = st.selectbox("Timeframe Operacional:", ["1h", "15m", "5m", "1m"], index=1)
    st.write("**Filtro Mestre:** Gráfico de 1 Hora (Macro)")
    ligar_bot = st.toggle("📲 Alertas Telegram c/ Print", value=True)

    if st.button("🧪 Testar Telegram"):
        enviar_alerta_completo("⚡ Sniper Ultimate: Teste de Conexão OK!")
        st.toast("Mensagem enviada!")

# --- 2. PROCESSAMENTO DE DADOS (MTF - DUPLO) ---
df_op = yf.download(ativo_p, period="1mo", interval=tf_op, progress=False)
df_macro = yf.download(ativo_p, period="2mo", interval="1h", progress=False)

if not df_op.empty and not df_macro.empty:
    if isinstance(df_op.columns, pd.MultiIndex): df_op.columns = df_op.columns.get_level_values(0)
    if isinstance(df_macro.columns, pd.MultiIndex): df_macro.columns = df_macro.columns.get_level_values(0)

    df_op = calcular_indicadores(df_op)
    df_macro = calcular_indicadores(df_macro)

    # Tendência do General (1H)
    macro_alta = df_macro['Close'].iloc[-1] > df_macro['EMA_200'].iloc[-1]

    # Lógica de Sinais c/ Filtro de Tendência 1H
    df_op['Sinal_Compra'] = False
    df_op['TP'], df_op['SL'] = 0.0, 0.0

    for i in range(1, len(df_op)):
        # Condições locais (5/5)
        c = [df_op['RSI'].iloc[i] < 60, df_op['EMA_FAST'].iloc[i] > df_op['EMA_SLOW'].iloc[i],
             df_op['MACD'].iloc[i] > df_op['Signal_MACD'].iloc[i], df_op['Volume'].iloc[i] > df_op['Vol_Med'].iloc[i],
             df_op['Close'].iloc[i] > df_op['EMA_FAST'].iloc[i]]

        # Validação no Macro (1H) para aquele horário
        hora_c = df_op.index[i]
        try:
            pos_m = df_macro.index.get_indexer([hora_c], method='pad')[0]
            m_ok = df_macro['Close'].iloc[pos_m] > df_macro['EMA_200'].iloc[pos_m]
        except:
            m_ok = macro_alta

        if all(c) and m_ok:
            if not (df_op['EMA_FAST'].iloc[i - 1] > df_op['EMA_SLOW'].iloc[i - 1]):
                df_op.at[df_op.index[i], 'Sinal_Compra'] = True
                df_op.at[df_op.index[i], 'SL'] = df_op['Close'].iloc[i] - (df_op['ATR'].iloc[i] * 2)
                df_op.at[df_op.index[i], 'TP'] = df_op['Close'].iloc[i] + (df_op['ATR'].iloc[i] * 4)

    # --- 3. DASHBOARD SUPERIOR ---
    st.title(f"📊 Dashboard Sniper: {ativo_p} ({tf_op})")
    wr, lucro_total = executar_backtest(df_op)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Preço Atual", f"{df_op['Close'].iloc[-1]:.2f}")
    m2.metric("Assertividade (MTF)", f"{wr:.1f}%")
    m3.metric("Saldo Estratégia", f"{lucro_total:.2f}%")
    m4.metric("Tendência Macro 1H", "ALTA" if macro_alta else "BAIXA",
              delta="AUTORIZADO" if macro_alta else "BLOQUEADO")

    # --- 4. GRÁFICO PROFISSIONAL ---
    df_plot = df_op.tail(100)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'],
                                 close=df_plot['Close'], name="Candles"))
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA_FAST'], name="EMA 5", line=dict(color='orange', width=1)))
    fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA_SLOW'], name="EMA 13", line=dict(color='purple', width=1)))

    # Marcando Sinais
    sinais_p = df_plot[df_plot['Sinal_Compra'] == True]
    if not sinais_p.empty:
        fig.add_trace(go.Scatter(x=sinais_p.index, y=sinais_p['Low'] * 0.992, mode='markers+text',
                                 text=[f"R${p:.2f}" for p in sinais_p['Close']], textposition="bottom center",
                                 marker=dict(symbol='triangle-up', size=25, color='lime',
                                             line=dict(width=2, color='white'))))

    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False,
                      margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

    # --- 5. LOGS E GESTÃO DE RISCO ---
    c_left, c_right = st.columns([2, 1])
    with c_left:
        st.subheader("📋 Histórico de Entradas Lateral")
        hist = df_op[df_op['Sinal_Compra'] == True][['Close', 'TP', 'SL']].tail(5)
        if not hist.empty:
            st.table(hist.sort_index(ascending=False))

    with c_right:
        st.subheader("✅ Checklist Sniper")
        last_row = df_op.iloc[-1]
        chks = [last_row['RSI'] < 60, last_row['EMA_FAST'] > last_row['EMA_SLOW'],
                last_row['MACD'] > last_row['Signal_MACD'], last_row['Volume'] > last_row['Vol_Med'], macro_alta]
        lbls = ["RSI < 60", "Média 5 > 13", "MACD Up", "Volume Up", "Tendência 1H"]
        for i in range(5):
            st.write(f"{'🟢' if chks[i] else '🔴'} {lbls[i]}")

    # --- 6. DISPARO AUTOMÁTICO TELEGRAM ---
    if ligar_bot and df_op['Sinal_Compra'].iloc[-1]:
        if "last_sig" not in st.session_state or st.session_state.last_sig != df_op.index[-1]:
            st.session_state.last_sig = df_op.index[-1]
            txt = f"🎯 SNIPER ULTIMATE ALERT!\n\n📈 Ativo: {ativo_p} ({tf_op})\n💰 Compra: {df_op['Close'].iloc[-1]:.2f}\n🛡️ Stop: {df_op['SL'].iloc[-1]:.2f}\n🎯 Alvo: {df_op['TP'].iloc[-1]:.2f}\n📊 WinRate: {wr:.1f}%"
            enviar_alerta_completo(txt, fig)

else:
    st.error("Erro ao carregar dados. Verifique sua conexão ou o nome do ativo.")
