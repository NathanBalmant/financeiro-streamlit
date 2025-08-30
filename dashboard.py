# dashboard.py
import streamlit as st
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px

# ------------------------------------
# CONFIG
# ------------------------------------
st.set_page_config(page_title="Dashboard de Investimentos", page_icon="💹", layout="wide")

def fmt_brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(v) else v

@st.cache_resource
def gs_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

# ✅ sem TTL (você controla quando recarregar)
@st.cache_data
def load_data(sheet_name="Planilha de organizacao financeira", tab_name="Patrimonio"):
    sheet = gs_client().open(sheet_name).worksheet(tab_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    # normalização
    df["Valor"] = (
        df["Valor"].astype(str)
        .str.replace("R$", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )
    df["Data"] = pd.to_datetime(df["Data"], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["Data"]).copy()
    for col in ["Banco", "Tipo de Investimento", "Caracteristica"]:
        if col not in df.columns:
            df[col] = "Não informado"
    return df

# cores fixas para bancos
BANK_COLORS = {
    "Nubank": "#820AD1",  # roxo
    "Inter": "#FF6A00"    # laranja
}

# ------------------------------------
# DADOS
# ------------------------------------
df = load_data()
if df.empty:
    st.warning("Não foi possível carregar dados.")
    st.stop()

# ------------------------------------
# TÍTULO + BOTÃO DE RELOAD
# ------------------------------------
st.title("📊 Dashboard de Patrimônio e Investimentos")

col_reload, _ = st.columns([1, 3])
with col_reload:
    if st.button("🔄 Recarregar dados"):
        load_data.clear()  # limpa o cache da função
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()

# ------------------------------------
# KPIs
# ------------------------------------
total_patrimonio = df["Valor"].sum()
top_bank = df.groupby("Banco")["Valor"].sum().sort_values(ascending=False).head(1)

c1, c2, c3 = st.columns(3)
c1.metric("Patrimônio Total", fmt_brl(total_patrimonio))
c2.metric("Qtd. Ativos", f"{df['Caracteristica'].nunique()}")
if not top_bank.empty:
    c3.metric("Maior Banco", f"{top_bank.index[0]} — {fmt_brl(top_bank.iloc[0])}")

st.markdown("---")

# ------------------------------------
# GRÁFICOS GERAIS
# ------------------------------------
# Evolução
evol = df.sort_values("Data").groupby("Data", as_index=False)["Valor"].sum()
evol["Patrimonio"] = evol["Valor"].cumsum()

evol["Data"] = evol["Data"].dt.date

fig_evol = px.line(evol, x="Data", y="Patrimonio", markers=True, title="Evolução do Patrimônio")
fig_evol.update_yaxes(tickprefix="R$ ", tickformat=",.2f")
# 👇 formata o eixo X no estilo dd/mm/yyyy
fig_evol.update_xaxes(tickformat="%d/%m/%Y")

# Distribuição por Banco
por_banco = df.groupby("Banco", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
fig_banco = px.bar(
    por_banco, x="Banco", y="Valor",
    color="Banco", color_discrete_map=BANK_COLORS,
    text_auto=".2s", title="Alocação por Banco"
)
fig_banco.update_yaxes(tickprefix="R$ ", tickformat=",.2f")

c1, c2 = st.columns(2)
c1.plotly_chart(fig_evol, use_container_width=True)
c2.plotly_chart(fig_banco, use_container_width=True)

# ----------------- NOVO BLOCO LADO A LADO -----------------
# Distribuição por Classe
dist_tipo = df.groupby("Tipo de Investimento", as_index=False)["Valor"].sum()
fig_tipo = px.pie(
    dist_tipo, names="Tipo de Investimento", values="Valor", hole=.45,
    title="Distribuição por Classe"
)

# Distribuição por Característica (Ativos)
dist_char_total = df.groupby("Caracteristica", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)

# (opcional) limitar para top 12 e somar o resto como "Outros" para não poluir
TOP_N = 12
if len(dist_char_total) > TOP_N:
    top = dist_char_total.head(TOP_N).copy()
    outros_valor = dist_char_total["Valor"].iloc[TOP_N:].sum()
    dist_char = pd.concat([top, pd.DataFrame([{"Caracteristica": "Outros", "Valor": outros_valor}])], ignore_index=True)
else:
    dist_char = dist_char_total

fig_char = px.pie(
    dist_char, names="Caracteristica", values="Valor", hole=.45,
    title="Distribuição por Características (Ativos)"
)

c1, c2 = st.columns(2)
c1.plotly_chart(fig_tipo, use_container_width=True)
c2.plotly_chart(fig_char, use_container_width=True)
# -----------------------------------------------------------

# Top 10 Ativos (R$)
top_ativos = dist_char_total.head(10)
fig_top = px.bar(
    top_ativos, x="Valor", y="Caracteristica",
    orientation="h", color="Caracteristica",
    text_auto=".2s", title="Top 10 Ativos (R$)"
)
fig_top.update_xaxes(tickprefix="R$ ", tickformat=",.2f")
st.plotly_chart(fig_top, use_container_width=True)

st.markdown("---")

# ------------------------------------
# DETALHAMENTO POR BANCO (TABELAS)
# ------------------------------------
st.subheader("📦 Detalhamento por Banco")
for banco in por_banco["Banco"]:
    df_b = df[df["Banco"] == banco].copy()
    total_banco = df_b["Valor"].sum()
    ativos_b = (
        df_b.groupby(["Caracteristica", "Tipo de Investimento"], as_index=False)["Valor"]
        .sum().sort_values("Valor", ascending=False)
    )
    ativos_b["% no banco"] = (ativos_b["Valor"] / total_banco * 100).round(1)
    st.markdown(f"**{banco} — Total {fmt_brl(total_banco)}**")
    st.dataframe(ativos_b, use_container_width=True)
    st.divider()

# ------------------------------------
# TABELA GERAL
# ------------------------------------
st.subheader("🔎 Dados Detalhados (Geral)")
st.dataframe(df.sort_values(["Data", "Banco"]), use_container_width=True)
