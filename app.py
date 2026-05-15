from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Análise Crédito Educativo",
    page_icon="🎓",
    layout="wide",
)

# =========================================================
# LEITURA ROBUSTA DO EXCEL
# =========================================================

@st.cache_data(show_spinner="Carregando planilha...")
def ler_excel(uploaded_file=None):
    if uploaded_file is not None:
        return pd.read_excel(uploaded_file)

    arquivos_xlsx = sorted(Path(".").glob("*.xlsx"))

    if not arquivos_xlsx:
        st.error("Não encontrei nenhum arquivo .xlsx na raiz do projeto.")
        st.info("No GitHub, deixe a planilha na mesma pasta do app.py. Exemplo: app.py, requirements.txt e a planilha .xlsx todos juntos.")
        st.stop()

    arquivo = arquivos_xlsx[0]
    st.sidebar.success(f"Planilha carregada: {arquivo.name}")
    return pd.read_excel(arquivo)


def limpar_numero(valor):
    if pd.isna(valor):
        return np.nan
    if isinstance(valor, (int, float, np.number)):
        return float(valor)

    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace("%", "").replace(" ", "")

    # Formato brasileiro: 1.234,56
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except Exception:
        return np.nan


def achar_coluna(df, termos):
    colunas = [str(c).strip() for c in df.columns]
    mapa_exato = {c.lower(): c for c in colunas}

    for termo in termos:
        termo = termo.lower().strip()
        if termo in mapa_exato:
            return mapa_exato[termo]

    for c in colunas:
        c_low = c.lower()
        for termo in termos:
            if termo.lower().strip() in c_low:
                return c

    return None


def classificar_risco(score):
    if score >= 75:
        return "Crítico"
    if score >= 55:
        return "Alto"
    if score >= 35:
        return "Médio"
    return "Baixo"


def motivo(row):
    motivos = []

    if row["Percentual Conclusão"] < 70:
        motivos.append("baixo percentual de conclusão")

    if row["Semestres utilizados pós dilatação"] < 0:
        motivos.append("semestres utilizados acima da dilatação")
    elif row["Semestres utilizados pós dilatação"] <= 1:
        motivos.append("pouca margem de semestres")

    if row["Semestres restantes"] <= 0:
        motivos.append("semestres restantes zerados")

    if row["Saldo Normalizado"] >= 70:
        motivos.append("saldo devedor alto")

    return ", ".join(motivos) if motivos else "acompanhar"


def moeda(valor):
    if pd.isna(valor):
        valor = 0
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(show_spinner="Tratando dados...")
def preparar_dados(df_original):
    df = df_original.copy()
    df.columns = [str(c).strip() for c in df.columns]

    col_matricula = achar_coluna(df, ["matricula", "matrícula"])
    col_nome = achar_coluna(df, ["nome", "aluno"])
    col_credito = achar_coluna(df, ["credito", "crédito"])
    col_curso = achar_coluna(df, ["nocurso", "curso"])
    col_situacao = achar_coluna(df, ["situação", "situacao"])
    col_percentual = achar_coluna(df, ["percentual %", "percentual", "%"])
    col_saldo = achar_coluna(df, ["saldo devedor", "saldo"])
    col_pos_dilatacao = achar_coluna(df, ["semestres utilizados pós dilatação", "pos dilatacao", "pós dilatação", "dilatação"])
    col_restantes = achar_coluna(df, ["semestres restantes", "restantes"])
    col_previsao = achar_coluna(df, ["previsão de formatura", "previsao de formatura", "formatura"])
    col_matriz = achar_coluna(df, ["semestres matriz curricular", "matriz curricular"])
    col_utilizados = achar_coluna(df, ["semestres de utilização em nº", "semestres de utilizacao em nº", "utilização", "utilizacao"])
    col_dilatacao = achar_coluna(df, ["semestre com dilatação", "semestre com dilatacao"])

    obrigatorias = {
        "Nome": col_nome,
        "Curso": col_curso,
        "Percentual de conclusão": col_percentual,
        "Saldo devedor": col_saldo,
        "Semestres utilizados pós dilatação": col_pos_dilatacao,
        "Semestres restantes": col_restantes,
    }

    faltando = [nome for nome, coluna in obrigatorias.items() if coluna is None]
    if faltando:
        st.error("Não consegui identificar todas as colunas necessárias.")
        st.write("Colunas faltando:", faltando)
        st.write("Colunas encontradas na planilha:", list(df.columns))
        st.stop()

    out = pd.DataFrame()
    out["Matrícula"] = df[col_matricula] if col_matricula else ""
    out["Nome"] = df[col_nome]
    out["Crédito"] = df[col_credito] if col_credito else ""
    out["Curso"] = df[col_curso]
    out["Situação"] = df[col_situacao] if col_situacao else ""
    out["Percentual Conclusão"] = df[col_percentual].apply(limpar_numero)
    out["Saldo devedor"] = df[col_saldo].apply(limpar_numero)
    out["Semestres utilizados pós dilatação"] = df[col_pos_dilatacao].apply(limpar_numero)
    out["Semestres restantes"] = df[col_restantes].apply(limpar_numero)
    out["Previsão formatura"] = df[col_previsao] if col_previsao else ""
    out["Semestres matriz"] = df[col_matriz].apply(limpar_numero) if col_matriz else np.nan
    out["Semestres utilizados"] = df[col_utilizados].apply(limpar_numero) if col_utilizados else np.nan
    out["Semestre com dilatação"] = df[col_dilatacao].apply(limpar_numero) if col_dilatacao else np.nan

    out = out.dropna(subset=["Percentual Conclusão"])
    out["Saldo devedor"] = out["Saldo devedor"].fillna(0)
    out["Semestres utilizados pós dilatação"] = out["Semestres utilizados pós dilatação"].fillna(0)
    out["Semestres restantes"] = out["Semestres restantes"].fillna(0)

    max_saldo = out["Saldo devedor"].max()
    out["Saldo Normalizado"] = np.where(max_saldo > 0, out["Saldo devedor"] / max_saldo * 100, 0)

    out["Gap Dilatação"] = out["Semestres utilizados pós dilatação"].apply(lambda x: abs(x) if x < 0 else 0)
    out["Alerta Semestre"] = out["Semestres utilizados pós dilatação"].apply(lambda x: 20 if x < 0 else 10 if x <= 1 else 0)
    out["Alerta Restante"] = out["Semestres restantes"].apply(lambda x: 15 if x <= 0 else 5 if x == 1 else 0)

    out["Score Criticidade"] = (
        ((100 - out["Percentual Conclusão"]) * 0.45)
        + (out["Saldo Normalizado"] * 0.25)
        + (out["Gap Dilatação"] * 8)
        + out["Alerta Semestre"]
        + out["Alerta Restante"]
    ).clip(0, 100)

    out["Faixa de Risco"] = out["Score Criticidade"].apply(classificar_risco)
    out["Motivo"] = out.apply(motivo, axis=1)

    return out


# =========================================================
# APP
# =========================================================

st.title("🎓 Análise de Crédito Educativo")
st.caption("Alunos com crédito educativo, conclusão abaixo de 85% e prazo de concessão encerrando em 2026/1")

with st.sidebar:
    st.header("Arquivo")
    uploaded_file = st.file_uploader("Enviar outra planilha Excel", type=["xlsx"])
    st.caption("Se não enviar nada, o app usa automaticamente o primeiro .xlsx encontrado na pasta do GitHub.")

try:
    df_original = ler_excel(uploaded_file)
    df = preparar_dados(df_original)
except Exception as e:
    st.error("Erro ao carregar ou tratar a planilha.")
    st.exception(e)
    st.stop()

with st.sidebar:
    st.header("Filtros")
    cursos_disponiveis = sorted(df["Curso"].dropna().astype(str).unique())
    cursos = st.multiselect("Curso", cursos_disponiveis, default=cursos_disponiveis)
    riscos = st.multiselect("Faixa de risco", ["Crítico", "Alto", "Médio", "Baixo"], default=["Crítico", "Alto", "Médio", "Baixo"])
    percentual_max = st.slider("Percentual máximo de conclusão", 0, 100, 85)
    saldo_min = st.number_input("Saldo mínimo", min_value=0.0, value=0.0, step=1000.0)

filtro = df[
    df["Curso"].astype(str).isin(cursos)
    & df["Faixa de Risco"].isin(riscos)
    & (df["Percentual Conclusão"] <= percentual_max)
    & (df["Saldo devedor"] >= saldo_min)
].copy()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Alunos filtrados", len(filtro))
col2.metric("Saldo total", moeda(filtro["Saldo devedor"].sum()))
col3.metric("Média conclusão", f"{filtro['Percentual Conclusão'].mean():.1f}%" if len(filtro) else "0%")
col4.metric("Casos críticos", len(filtro[filtro["Faixa de Risco"] == "Crítico"]))
col5.metric("Score médio", f"{filtro['Score Criticidade'].mean():.1f}" if len(filtro) else "0")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["Visão geral", "Ranking de risco", "Cursos", "Base detalhada"])

with tab1:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Distribuição por faixa de risco")
        ordem = ["Crítico", "Alto", "Médio", "Baixo"]
        dist = filtro["Faixa de Risco"].value_counts().reindex(ordem).fillna(0).reset_index()
        dist.columns = ["Faixa de Risco", "Quantidade"]
        fig = px.bar(dist, x="Faixa de Risco", y="Quantidade", text="Quantidade")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Percentual de conclusão x saldo devedor")
        fig = px.scatter(
            filtro,
            x="Percentual Conclusão",
            y="Saldo devedor",
            color="Faixa de Risco",
            size="Score Criticidade",
            hover_data=["Nome", "Curso", "Semestres utilizados pós dilatação", "Semestres restantes", "Motivo"],
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Distribuição do percentual de conclusão")
    fig = px.histogram(filtro, x="Percentual Conclusão", nbins=12)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Top alunos mais sensíveis")
    top_n = st.slider("Quantidade no ranking", 5, 50, 20)
    ranking = filtro.sort_values("Score Criticidade", ascending=False).head(top_n)

    fig = px.bar(
        ranking.sort_values("Score Criticidade"),
        x="Score Criticidade",
        y="Nome",
        orientation="h",
        hover_data=["Curso", "Percentual Conclusão", "Saldo devedor", "Motivo"],
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        ranking[[
            "Matrícula", "Nome", "Curso", "Percentual Conclusão", "Saldo devedor",
            "Semestres utilizados pós dilatação", "Semestres restantes", "Score Criticidade",
            "Faixa de Risco", "Motivo",
        ]],
        use_container_width=True,
        hide_index=True,
    )

with tab3:
    st.subheader("Resumo por curso")
    resumo = filtro.groupby("Curso", as_index=False).agg(
        Alunos=("Nome", "count"),
        Saldo_Total=("Saldo devedor", "sum"),
        Media_Conclusao=("Percentual Conclusão", "mean"),
        Score_Medio=("Score Criticidade", "mean"),
        Criticos=("Faixa de Risco", lambda x: (x == "Crítico").sum()),
    )
    resumo = resumo.sort_values(["Criticos", "Score_Medio", "Saldo_Total"], ascending=False)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(resumo.head(15), x="Curso", y="Criticos", text="Criticos")
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(resumo.head(15), x="Curso", y="Saldo_Total", text_auto=".2s")
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(resumo, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Base detalhada")
    busca = st.text_input("Buscar por nome, matrícula ou curso")
    detalhe = filtro.copy()

    if busca:
        termo = busca.lower()
        detalhe = detalhe[
            detalhe["Nome"].astype(str).str.lower().str.contains(termo, na=False)
            | detalhe["Matrícula"].astype(str).str.lower().str.contains(termo, na=False)
            | detalhe["Curso"].astype(str).str.lower().str.contains(termo, na=False)
        ]

    st.dataframe(detalhe.sort_values("Score Criticidade", ascending=False), use_container_width=True, hide_index=True)

    csv = detalhe.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Baixar base filtrada em CSV",
        data=csv,
        file_name="analise_credito_educativo_filtrada.csv",
        mime="text/csv",
    )

st.divider()
st.caption("Score inicial: baixo percentual de conclusão + saldo devedor + semestres pós dilatação + semestres restantes. Os pesos podem ser ajustados depois.")
