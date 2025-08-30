# dashboard.py
import streamlit as st
import pandas as pd
import numpy as np
import io

import plotly.express as px

# ------------------------------------
# CONFIG
# ------------------------------------
st.set_page_config(page_title="Dashboard de Investimentos", page_icon="💹", layout="wide")

# --- Gate simples por senha (opcional) ---
def require_login():
    secret = st.secrets.get("APP_PASSWORD")
    if not secret:
        return  # sem senha definida nos Secrets, não bloqueia
    if st.session_state.get("auth_ok"):
        return
    with st.sidebar:
        st.header("🔐 Acesso")
        pwd = st.text_input("Senha", type="password", placeholder="Digite a senha")
        if st.button("Entrar"):
            if pwd.strip() == str(secret).strip():
                st.session_state["auth_ok"] = True
                st.rerun()
            else:
                st.error("Senha inválida.")
    if not st.session_state.get("auth_ok"):
        st.stop()

require_login()

# ------------------------------------
# UTILS
# ------------------------------------
def fmt_brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(v) else v

def clean_money_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.replace("R$", "", regex=False)
        .str.replace(".", "", regex=False)     # separador de milhar
        .str.replace(",", ".", regex=False)    # decimal pt-BR -> ponto
        .str.strip()
        .replace({"": np.nan})
        .astype(float)
    )

# Cores fixas para bancos
BANK_COLORS = {
    "Nubank": "#820AD1",  # roxo
    "Inter":  "#FF6A00",  # laranja
}

# ------------------------------------
# SIDEBAR — UPLOAD E MAPEAMENTO
# ------------------------------------
st.sidebar.header("📥 Dados")
uploaded = st.sidebar.file_uploader(
    "Envie seu CSV (UTF-8, ; ou ,)",
    type=["csv"],
    help="Pode usar ; ou , como separador. O app tenta detectar automaticamente.",
)

# Opções de layout responsivo
st.sidebar.header("🧩 Layout")
empilhar = st.sidebar.toggle("Empilhar gráficos (mobile)", value=False)
top_n_caracteristicas = st.sidebar.slider("Top N ativos no donut de Características", 6, 20, 12, 1)

# Early stop se não tiver arquivo
if not uploaded:
    st.title("📊 Dashboard de Patrimônio e Investimentos")
    st.info("Envie um arquivo **.csv** na barra lateral para visualizar o dashboard.")
    st.stop()

# ------------------------------------
# LEITURA DO CSV (detecção automática)
# ------------------------------------
raw = uploaded.read()

# tenta UTF-8, depois latin-1
for enc in ("utf-8", "latin-1"):
    try:
        buffer = io.StringIO(raw.decode(enc))
        # sep=None com engine='python' tenta deduzir ; ou ,
        df = pd.read_csv(buffer, sep=None, engine="python")
        break
    except Exception:
        df = None

if df is None or df.empty:
    st.error("Não foi possível ler o CSV. Verifique codificação (UTF-8/latin-1) e separador (; ou ,).")
    st.stop()

# ------------------------------------
# MAPEAMENTO DE COLUNAS
# ------------------------------------
st.sidebar.header("🧭 Mapeamento de colunas")
cols = df.columns.tolist()

def pick(label, default_guess):
    guess = default_guess if default_guess in cols else (cols[0] if cols else None)
    return st.sidebar.selectbox(label, options=cols, index=cols.index(guess) if guess in cols else 0)

# tentativas de nomes comuns
data_col = pick("Coluna de Data", next((c for c in cols if c.lower() in ["data", "date"]), cols[0]))
valor_col = pick("Coluna de Valor (R$)", next((c for c in cols if "valor" in c.lower()), cols[0]))
banco_col = pick("Coluna de Banco", next((c for c in cols if "banco" in c.lower()), cols[0]))
classe_col = pick("Coluna de Classe (Tipo de Investimento)", next((c for c in cols if "tipo" in c.lower()), cols[0]))
caract_col = pick("Coluna de Característica (Ativo)", next((c for c in cols if "caracter" in c.lower() or "ativo" in c.lower()), cols[0]))

# ------------------------------------
# NORMALIZAÇÃO
# ------------------------------------
work = df[[data_col, valor_col, banco_col, classe_col, caract_col]].copy()
work.columns = ["Data", "Valor", "Banco", "Tipo de Investimento", "Caracteristica"]

# Valor
try:
    work["Valor"] = clean_money_series(work["Valor"])
except Exception:
    st.error("Não consegui converter a coluna de Valor para número. Verifique o CSV.")
    st.stop()

# Data
# tenta dd/mm/yyyy e yyyy-mm-dd automaticamente
work["Data"] = pd.to_datetime(work["Data"], errors="coerce", dayfirst=True)
if work["Data"].isna().all():
    # fallback sem dayfirst
    work["Data"] = pd.to_datetime(work["Data"], errors="coerce", dayfirst=False)
work = work.dropna(subset=["Data"]).copy()

# Completa colunas ausentes com texto padrão
for col in ["Banco", "Tipo de Investimento", "Caracteristica"]:
    work[col] = work[col].fillna("Não informado").astype(str)

# ------------------------------------
# DASHBOARD
# ------------------------------------
st.title("📊 Dashboard de Patrimônio e Investimentos")

# Botão de recarregar (no caso de enviar outro CSV com o mesmo nome durante a sessão)
if st.button("🔄 Recarregar (limpar cache e reiniciar)"):
    st.cache_data.clear()
    st.rerun()

# KPIs
total_patrimonio = work["Valor"].sum()
top_bank = work.groupby("Banco")["Valor"].sum().sort_values(ascending=False).head(1)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Patrimônio Total", fmt_brl(total_patrimonio))
k2.metric("Qtd. Ativos", f"{work['Caracteristica'].nunique()}")
k3.metric("Qtd. Bancos", f"{work['Banco'].nunique()}")
k4.metric("Maior Banco", f"{top_bank.index[0]} — {fmt_brl(top_bank.iloc[0])}" if not top_bank.empty else "—")

st.markdown("---")

# Evolução do patrimônio (acumulado por dia)
evol = (
    work.sort_values("Data")
        .groupby("Data", as_index=False)["Valor"].sum()
        .assign(Patrimonio=lambda d: d["Valor"].cumsum())
)
# mostrar só dia
evol["Data"] = evol["Data"].dt.date

fig_evol = px.line(evol, x="Data", y="Patrimonio", markers=True, title="Evolução do Patrimônio")
fig_evol.update_yaxes(tickprefix="R$ ", tickformat=",.2f")
fig_evol.update_xaxes(tickformat="%d/%m/%Y")

# Alocação por banco
por_banco = work.groupby("Banco", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
fig_banco = px.bar(
    por_banco, x="Banco", y="Valor",
    color="Banco", color_discrete_map=BANK_COLORS,
    text_auto=".2s", title="Alocação por Banco"
)
fig_banco.update_yaxes(tickprefix="R$ ", tickformat=",.2f")

if empilhar:
    st.plotly_chart(fig_evol, use_container_width=True)
    st.plotly_chart(fig_banco, use_container_width=True)
else:
    c1, c2 = st.columns(2)
    c1.plotly_chart(fig_evol, use_container_width=True)
    c2.plotly_chart(fig_banco, use_container_width=True)

# Donuts: Classe & Característica (lado a lado)
dist_tipo = work.groupby("Tipo de Investimento", as_index=False)["Valor"].sum()
fig_tipo = px.pie(dist_tipo, names="Tipo de Investimento", values="Valor", hole=.45, title="Distribuição por Classe")

dist_char_total = work.groupby("Caracteristica", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
if len(dist_char_total) > top_n_caracteristicas:
    top = dist_char_total.head(top_n_caracteristicas).copy()
    outros_valor = dist_char_total["Valor"].iloc[top_n_caracteristicas:].sum()
    dist_char = pd.concat([top, pd.DataFrame([{"Caracteristica": "Outros", "Valor": outros_valor}])], ignore_index=True)
else:
    dist_char = dist_char_total
fig_char = px.pie(dist_char, names="Caracteristica", values="Valor", hole=.45, title="Distribuição por Características (Ativos)")

if empilhar:
    st.plotly_chart(fig_tipo, use_container_width=True)
    st.plotly_chart(fig_char, use_container_width=True)
else:
    c1, c2 = st.columns(2)
    c1.plotly_chart(fig_tipo, use_container_width=True)
    c2.plotly_chart(fig_char, use_container_width=True)

# Top 10 ativos (R$)
top_ativos = dist_char_total.head(10)
fig_top = px.bar(
    top_ativos, x="Valor", y="Caracteristica",
    orientation="h", color="Caracteristica",
    text_auto=".2s", title="Top 10 Ativos (R$)"
)
fig_top.update_xaxes(tickprefix="R$ ", tickformat=",.2f")
st.plotly_chart(fig_top, use_container_width=True)

st.markdown("---")

# Detalhamento por banco (tabelas simples)
st.subheader("📦 Detalhamento por Banco")
for banco in por_banco["Banco"]:
    df_b = work[work["Banco"] == banco].copy()
    total_banco = df_b["Valor"].sum()
    ativos_b = (
        df_b.groupby(["Caracteristica", "Tipo de Investimento"], as_index=False)["Valor"]
            .sum().sort_values("Valor", ascending=False)
    )
    ativos_b["% no banco"] = (ativos_b["Valor"] / total_banco * 100).round(1)
    st.markdown(f"**{banco} — Total {fmt_brl(total_banco)}**")
    st.dataframe(ativos_b, use_container_width=True)
    st.divider()

# Tabela geral
st.subheader("🔎 Dados Detalhados (Geral)")
st.dataframe(work.sort_values(["Data", "Banco", "Tipo de Investimento", "Caracteristica"]), use_container_width=True)
